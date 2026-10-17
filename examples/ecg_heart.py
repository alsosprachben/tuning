#!/usr/bin/env python3
"""The SFX set's Heart Beat (program 56, key 55) as the heart's own
waveform: a standard ECG beat, its Fourier series by FFT, written as the
class's partials (tonelib.SfxHeartbeatProperties).

    python3 -I examples/ecg_heart.py            the series, and how well it rebuilds the beat
    python3 -I examples/ecg_heart.py --write    ...into tonelib.py
    python3 -I examples/ecg_heart.py --check    render the key and compare it to the beat

THE BEAT, lead II, textbook intervals at 60 bpm (one beat a second, the
key's fundamental 1 Hz): each wave a Gaussian (centre s re the R peak,
height mV, width sigma s) --

    P   -0.180   0.15   0.025     atria (PR interval 0.16 s)
    Q   -0.025  -0.10   0.008
    R    0       1.00   0.010     the ventricles (QRS ~0.09 s)
    S   +0.025  -0.25   0.008
    T   +0.280   0.30   0.045     their recovery (QT ~0.38 s)

placed so the P wave starts ~0.1 s into the beat and everything is back at
the baseline before it ends: one period, the note gated to it. The series
is sampled at 1 Hz harmonics to 80 Hz, where the R wave's spectrum is 60 dB
down; the DC dropped (a speaker passes none).

THE BLOOD FLOW over it (Ben: "Can we simulate blood flow on top of the
shape?"), as a Doppler probe hears it -- the "whoosh" of a fetal or vascular
Doppler, which is the flow's velocity made audible: the spectrum fills from 0
to a top frequency that follows the velocity. The velocity, an artery's
(carotid-like, re its peak): the ventricles eject from 60 ms after R,
peaking at 130 ms (rising over ~35 ms, falling over ~70), done by the T
wave's end; a dip as the aortic valve shuts (the dicrotic notch); then
diastole's forward flow, a quarter of the peak, dying away to the next beat.
The top: 3 kHz at the peak. Built from third-octave noise bands, 200 Hz to
2.5 kHz, each sounding over the spans the top reaches it (FLOW_EVENTS:
tonelib.SfxHeartbeatProperties.noise_events), equal in level (the Doppler's
fill), ramped 20 ms.

Ben: "take a standard ECG shape, and use an FFT to convert it. Let's just
make it the actual waveform." So nothing is shaped for the ear: most of the
beat's energy is under 20 Hz, and what a speaker gives back is the QRS's
upper spectrum -- a soft knock -- and the T wave's slow swell.
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

RATE = 1.0                  # Hz: 60 bpm
R_AT = 0.30                 # s into the beat
WAVES = ((-0.180, 0.15, 0.025), (-0.025, -0.10, 0.008), (0.0, 1.00, 0.010),
         (0.025, -0.25, 0.008), (0.280, 0.30, 0.045))
N = 80                      # harmonics
SR = 8192                   # the beat's samples (a power of two a period)


FLOW_TOP_HZ = 3000.0
FLOW_BANDS = tuple(200.0 * 2.0 ** (k / 3.0) for k in range(12))      # 200 Hz-2.5 kHz


def velocity(t):
    """The artery's flow velocity re its peak at times t (s into the beat)."""
    # PERIODIC, as the trace is: diastole runs on into the next beat's start
    # (before its R), so beats in a row flow without a gap
    r = np.mod(t - R_AT, 1.0 / RATE)
    pk = 0.13
    sys_ = np.exp(-0.5 * ((r - pk) / np.where(r < pk, 0.035, 0.07)) ** 2)
    # the valve shuts: a dip at 0.34 s, then diastole's run-off, a quarter of
    # the peak decaying (0.35 s) toward the next beat
    dia = 0.25 * np.clip((r - 0.34) / 0.03, 0.0, 1.0) * np.exp(-np.clip(r - 0.37, 0.0, None) / 0.35)
    return np.maximum(sys_, dia)


def flow_events():
    """(Hz, dB, start s, end s): each band over the spans the Doppler top
    (FLOW_TOP_HZ x velocity) reaches it, 0 dB each."""
    t = np.arange(SR) / (SR * RATE)
    top = FLOW_TOP_HZ * velocity(t)
    out = []
    for f in FLOW_BANDS:
        on = np.concatenate([[False], top > f, [False]])
        d = np.diff(on.astype(int))
        for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            if (b - a) / SR >= 0.02:
                out.append((round(f, 1), 0.0, round(a / SR, 4), round(b / SR, 4)))
    return tuple(out)


def beat(t):
    """The ECG at times t (s, one period from 0), mV."""
    x = np.zeros_like(t)
    for c, a, s in WAVES:
        for k in (-1, 0, 1):        # wrapped: the period repeats
            x += a * np.exp(-0.5 * ((t - R_AT - c + k / RATE) / s) ** 2)
    return x


def series():
    """(gains re the strongest, phases rad) for harmonics 1..N, as cos(k w t + phase)."""
    t = np.arange(SR) / (SR * RATE)
    X = np.fft.rfft(beat(t)) / SR
    a = 2.0 * np.abs(X[1:N + 1])
    ph = np.angle(X[1:N + 1])
    return a / a.max(), ph, a.max()


def rebuild(g, ph, t):
    return sum(gk * np.cos(2 * np.pi * (k + 1) * RATE * t + pk) for k, (gk, pk) in enumerate(zip(g, ph)))


def main(argv):
    g, ph, top = series()
    t = np.arange(SR) / (SR * RATE)
    x = beat(t)
    y = rebuild(g, ph, t) * top
    err = np.sqrt(np.mean((x - x.mean() - y) ** 2)) / np.ptp(x)
    print("  %d harmonics of %.1f Hz: rebuilt to %.2f%% rms of the beat's swing" % (N, RATE, 100 * err))
    print("  gains dB (h1-h20): " + " ".join("%.0f" % (20 * np.log10(v)) for v in g[:20]))
    ev = flow_events()
    for f in (FLOW_BANDS[0], FLOW_BANDS[-1]):
        print("  the flow at %.0f Hz: %s" % (f, ", ".join("%.3f-%.3f s" % (e[2], e[3]) for e in ev if e[0] == round(f, 1))))
    if "--write" in argv:
        p = os.path.join(HERE, "tonelib.py")
        s = open(p).read()
        i = s.index("class SfxHeartbeatProperties(")
        j = s.index("\n\n\n", i)
        b = s[i:j]
        b = re.sub(r"    ECG_GAINS = .*\n", "    ECG_GAINS = (%s)\n" % ", ".join("%.5g" % v for v in g), b)
        b = re.sub(r"    ECG_PHASES = .*\n", "    ECG_PHASES = (%s)\n" % ", ".join("%.5f" % v for v in ph), b)
        b = re.sub(r"    FLOW_EVENTS = .*\n", "    FLOW_EVENTS = %r\n" % (flow_events(),), b)
        open(p, "w").write(s[:i] + b + s[j:])
        print("  wrote SfxHeartbeatProperties")
    if "--check" in argv:
        check(x - x.mean())
    return 0


def check(x):
    """Render key 55 and lay it over the beat: the correlation of the two, one
    period from the note's onset."""
    import mido
    import tempfile
    os.environ.setdefault("TUNING_REFLECT", "0")
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=9, program=56, time=0))
    tr.append(mido.Message("note_on", channel=9, note=55, velocity=100, time=480))
    tr.append(mido.Message("note_off", channel=9, note=55, velocity=0, time=240))
    tr.append(mido.MetaMessage("end_of_track", time=2000))
    d = tempfile.mkdtemp()
    path = os.path.join(d, "h.mid")
    m.save(path)
    L, R = B.render(path)[:2]
    y = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    on = int(0.5 * B.SR)
    y = y[on:on + int(B.SR / RATE)]
    xs = np.interp(np.arange(len(y)) / B.SR, np.arange(len(x)) / (SR * RATE), x)
    c = np.corrcoef(xs[: len(y)], y)[0, 1]
    lag = int(np.argmax(np.correlate(y, xs, "full"))) - (len(y) - 1)
    print("  rendered against the beat: correlation %.3f, lag %.1f ms; peak %.3f" % (c, 1000.0 * lag / B.SR, np.abs(y).max()))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
