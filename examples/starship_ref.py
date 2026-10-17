#!/usr/bin/env python3
"""The SFX set's Starship (key 71) as GeneralUser GS's patch means it: a
reference to fit to, there being no recording of a starship.

    python3 -I examples/starship_ref.py OUT.wav

Timidity plays GU's key wrong -- the noise sample once (its zone has loop
points but no sampleModes, 0.21 s) and the second layer's 12-sample loop as a
steady 4409 Hz tone with none of its modulation -- so this reads the two
zones' samples out of the SF2 (measured only, never redistributed) and plays
them by their generators:

  "Starship Noise"  looped (2625-9220), +1 semitone, through the SF2 two-pole
                    low-pass at 10628 cents (3.79 kHz) with 12.8 dB of
                    resonance, a 0.21 s attack, 6 dB down
  "Harpsi_2-C6"     its 12-sample loop (a buzz at 3675 Hz) played at key 71
                    on root 60 with coarse -19 (x 2^(-8/12): 2315 Hz), the mod
                    LFO swinging it 581 cents at 10.9 Hz, through a 1281 Hz
                    low-pass, a 0.84 s attack, 20 dB down

The mod envelope's slow terms (an octave up and +697 cents of cutoff over 16
s) move it under 80 cents in the 1.5 s played, and are left out.
"""
import os
import struct
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
SR = 44100
SECS = 1.5


def samples(path):
    """{name: (int16 array, loop start, loop end)} from the SF2's shdr/smpl."""
    d = open(path, "rb").read()
    top = {}
    o = 12
    while o < len(d):
        cid, n = d[o:o + 4], struct.unpack("<I", d[o + 4:o + 8])[0]
        if cid == b"LIST":
            p = o + 12
            while p < o + 8 + n:
                c2, n2 = d[p:p + 4], struct.unpack("<I", d[p + 4:p + 8])[0]
                top[c2] = (p + 8, n2)
                p += 8 + n2 + (n2 & 1)
        o += 8 + n + (n & 1)
    so, _ = top[b"smpl"]
    ho, hn = top[b"shdr"]
    out = {}
    for i in range(hn // 46):
        name, s0, s1, l0, l1 = struct.unpack("<20sIIII", d[ho + 46 * i:ho + 46 * i + 36])
        name = name.split(b"\0")[0].decode(errors="replace")
        out[name] = (np.frombuffer(d[so + 2 * s0:so + 2 * s1], "<i2").astype(np.float64) / 32768.0,
                     l0 - s0, l1 - s0)
    return out


def looped(x, l0, l1, ratio, n, cents=None):
    """The sample played at RATIO (times a per-sample 2^(cents/1200)), its
    loop repeating, linear interpolation."""
    step = np.full(n, ratio) if cents is None else ratio * 2.0 ** (cents / 1200.0)
    pos = np.concatenate(([0.0], np.cumsum(step)[:-1]))
    over = pos >= l1
    pos[over] = l0 + np.mod(pos[over] - l0, l1 - l0)
    i = np.floor(pos).astype(int)
    fr = pos - i
    return x[i] * (1 - fr) + x[np.minimum(i + 1, len(x) - 1)] * fr


def sf2_lowpass(x, fc_cents, q_cb=0.0):
    """The SF2 two-pole low-pass: cutoff in absolute cents, resonance in cB
    of peak over the DC gain."""
    fc = 8.176 * 2.0 ** (fc_cents / 1200.0)
    q = max(0.7071, 10.0 ** (q_cb / 200.0))
    w = 2 * np.pi * fc / SR
    a = np.sin(w) / (2 * q)
    b = np.array([(1 - np.cos(w)) / 2, 1 - np.cos(w), (1 - np.cos(w)) / 2])
    den = np.array([1 + a, -2 * np.cos(w), 1 - a])
    return lfilter(b / den[0], den / den[0], x)


def main(argv):
    out = argv[1] if len(argv) > 1 else "starship_ref.wav"
    S = samples(GU)
    n = int(SECS * SR)
    t = np.arange(n) / SR
    x, l0, l1 = S["Starship Noise"]
    noise = sf2_lowpass(looped(x, l0, l1, 2.0 ** (1 / 12.0), n), 10628, 128)
    noise *= np.minimum(1.0, t / 0.212) * 10 ** (-6 / 20.0)
    x, l0, l1 = S["Harpsi_2-C6"]
    lfo = 581.0 * np.sin(2 * np.pi * 10.9 * t)
    tone = sf2_lowpass(looped(x, l0, l1, 2.0 ** (-8 / 12.0), n, lfo), 8749)
    tone *= np.minimum(1.0, t / 0.84) * 10 ** (-20 / 20.0)
    y = noise + tone
    r = int(0.05 * SR)
    y[-r:] *= np.linspace(1, 0, r)
    wavfile.write(out, SR, (0.9 * y / np.abs(y).max() * 32767).astype(np.int16))
    print("  -> %s  (noise %.1f dB, tone %.1f dB rms)"
          % (out, 10 * np.log10(np.mean(noise ** 2)), 10 * np.log10(np.mean(tone ** 2))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
