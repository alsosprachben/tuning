#!/usr/bin/env python3
"""The diffuse tail, derived from the room rather than dialled in.

`blockrender` computes first-order reflections geometrically, per partial, with
each image carrying the spectrum the instrument actually radiated toward its
wall. That is the part where direction still matters. It stops mattering after
that: every scattering event randomises direction, so by the second or third
bounce the field is approximately DIFFUSE -- the same everywhere in the room, by
definition. Carrying per-source directional identity into high-order images is
not merely expensive, it asserts information that has physically stopped
existing. So the late field is one convolution, and that is the correct model
rather than a shortcut.

Nothing here is a taste control. Each number comes from the room already
declared in `tonelib.SynthProperties`:

  decay    Eyring's T60 per octave from the surface areas, their absorption
           coefficients, and air absorption over the mean free path. The hall
           in tonelib gives 2.09 s at 125 Hz falling to 1.30 s at 4 kHz --
           bass-rich and HF-damped, which is what a real hall does.

  level    the room constant R = S*alpha/(1-alpha) sets the reverberant field
           against the direct sound at the source distance. No wet/dry knob.

  onset    the mixing time, about sqrt(V) ms, which is where a geometric
           description stops being meaningful and the statistical one starts.
           For this hall that is ~102 ms, and the first-order images arrive
           between 1 and 87 ms, so the two meet without a gap.

The first-order images do double-count slightly, since Eyring's reverberant
field includes them. Measured on this room they contribute about 2.7% of the
reverberant energy, which is -15 dB into a term that is itself an estimate.

Usage:
    python3 roomtail.py IN.wav OUT.wav [--q 2.0] [--seed 0]
"""

import math
import os
import sys
import wave

import numpy as np

import tonelib as T

OCTAVES = (63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)


def room_of(props):
    """Dimensions, surface areas and volume from the declared room."""
    w = props.room_left + props.room_right
    d = props.room_front + props.room_back
    h = props.room_ceiling + props.room_floor
    areas = {'floor': w * d, 'ceiling': w * d,
             'left': d * h, 'right': d * h,
             'front': w * h, 'back': w * h}
    return w * d * h, areas


def decay_and_level(props, q=2.0, band_q=None):
    """[(centre Hz, T60 s, reverberant/direct energy ratio)] per octave.

    `band_q` is the measured directivity factor per band, written by
    blockrender as a sidecar: how much louder the sources were toward the
    listener than toward the room, averaged over what the piece actually
    played. It replaces the scalar `q`, which had to stand for every
    instrument at every frequency at once -- and stood badly, since Q runs from
    1.0 in the bass to about 15 at 8 kHz for a horn. Because the reverberant
    ratio goes as 1/Q, getting this right is what makes a hall bass-wet and
    treble-dry, which is most of why halls sound warm.
    """
    volume, areas = room_of(props)
    surface = sum(areas.values())
    r = props.radiation_distance
    out = []
    for f in OCTAVES:
        qf = band_q.get(f, q) if band_q else q
        absorbed = sum(a * props._octave_interp(props.SURFACE_ALPHA[s], f)
                       for s, a in areas.items())
        mean = absorbed / surface
        # Air absorption enters as nepers per metre, not decibels.
        m = props.air_absorption_db_per_m(f) / 8.685889638
        denom = -surface * math.log(max(1e-6, 1.0 - mean)) + 4.0 * m * volume
        t60 = 0.161 * volume / denom
        # Reverberant field against direct at r: (4/R) / (Q/(4*pi*r^2)).
        R = surface * mean / max(1e-6, 1.0 - mean)
        ratio = 16.0 * math.pi * r * r / (max(qf, 1e-3) * R)
        out.append((f, t60, ratio))
    return out


def build_ir(props, sr, q=2.0, seed=0, channels=2, band_q=None):
    """A diffuse impulse response: band-limited noise, each octave decaying at
    its own T60 and carrying its own share of the reverberant energy.

    Independent noise per channel, because a diffuse field is uncorrelated
    between two points a head apart -- that lack of correlation IS the sense of
    being surrounded, and sharing one noise sequence would collapse it to the
    middle of the head.
    """
    bands = decay_and_level(props, q, band_q)
    volume, _ = room_of(props)
    t60_max = max(b[1] for b in bands)
    onset = math.sqrt(volume) / 1000.0          # mixing time, seconds
    n = int((onset + t60_max * 1.2) * sr)
    t = np.arange(n) / float(sr)

    # The statistical field does not switch on; it takes over from the
    # geometric one across the mixing time.
    gate = np.clip((t - onset * 0.5) / max(onset * 0.5, 1e-6), 0.0, 1.0)
    gate = gate * gate * (3.0 - 2.0 * gate)     # smoothstep

    rng = np.random.RandomState(seed)
    ir = np.zeros((n, channels))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    for ci in range(channels):
        noise = rng.randn(n)
        spec = np.fft.rfft(noise)
        acc = np.zeros(n)
        for i, (fc, t60, ratio) in enumerate(bands):
            lo = fc / math.sqrt(2.0)
            hi = fc * math.sqrt(2.0)
            if lo >= sr / 2.0:
                continue
            hi = min(hi, sr / 2.0)
            mask = (freqs >= lo) & (freqs < hi)
            if not mask.any():
                continue
            band = np.fft.irfft(np.where(mask, spec, 0.0), n)
            band *= gate * np.exp(-6.907755 * t / max(t60, 1e-3))
            # NORMALISE THE MEAN-SQUARE GAIN IN THE BAND, NOT THE TOTAL ENERGY.
            # sum(h^2) is the integral of |H|^2 over the band, so equating it to
            # the ratio gives a band that is too loud by the reciprocal of the
            # band's share of the spectrum -- 495x at 63 Hz, where the octave is
            # 44 Hz of 22 kHz. Measured before the fix: +26.9 dB at 63 Hz and
            # +5.9 dB at 8 kHz, both exactly 10*log10(nyquist/width).
            share = (hi - lo) / (sr / 2.0)
            e = float((band * band).sum())
            if e > 0.0 and share > 0.0:
                acc += band * math.sqrt(ratio * share / e)
        ir[:, ci] = acc
    return ir, bands, onset


def overlap_add(x, h):
    """FFT convolution in blocks, so a nine-minute render does not need a
    thirty-million-point transform."""
    n = len(h)
    block = 1 << (int(math.ceil(math.log2(max(n, 2)))) + 2)
    step = block - n + 1
    H = np.fft.rfft(h, block)
    out = np.zeros(len(x) + n - 1)
    for i in range(0, len(x), step):
        seg = x[i:i + step]
        y = np.fft.irfft(np.fft.rfft(seg, block) * H, block)
        m = min(len(y), len(out) - i)
        out[i:i + m] += y[:m]
    return out[:len(x)]


def read_wav(path):
    w = wave.open(path, 'rb')
    n, sw, sr, ch = (w.getnframes(), w.getsampwidth(),
                     w.getframerate(), w.getnchannels())
    raw = w.readframes(n)
    w.close()
    if sw == 4:
        a = np.frombuffer(raw, '<i4').astype(np.float64) / 2147483647.0
    elif sw == 2:
        a = np.frombuffer(raw, '<i2').astype(np.float64) / 32767.0
    else:
        raise SystemExit("%s: unsupported sample width %d" % (path, sw))
    return a.reshape(-1, ch), sr


def write_wav(path, data, sr):
    n, ch = data.shape
    w = wave.open(path, 'wb')
    w.setnchannels(ch); w.setsampwidth(4); w.setframerate(sr)
    w.writeframes((np.clip(data, -1, 1).reshape(-1) * 2147483647.0)
                  .astype('<i4').tobytes())
    w.close()


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1])
        return 2
    inp, outp = argv[1], argv[2]
    q = float(argv[argv.index('--q') + 1]) if '--q' in argv else 2.0
    seed = int(argv[argv.index('--seed') + 1]) if '--seed' in argv else 0

    x, sr = read_wav(inp)
    props = T.StoppedPipeProperties(261.6, 0, 1, 1)
    # Prefer what the render measured over the scalar.
    band_q = None
    side = os.path.splitext(inp)[0] + '.room.json'
    if os.path.exists(side):
        import json
        d = json.load(open(side))
        band_q = {b['hz']: b['q'] for b in d['bands'] if b.get('energy', 0) > 0}
        print("   directivity factor from %s" % os.path.basename(side))
    ir, bands, onset = build_ir(props, sr, q=q, seed=seed,
                                channels=x.shape[1], band_q=band_q)

    volume, areas = room_of(props)
    print("== %s -> %s" % (inp, outp))
    print("   hall %.0f m3, %.0f m2 of surface, sources at %.0f m, Q=%.1f"
          % (volume, sum(areas.values()), props.radiation_distance, q))
    print("   tail starts at the mixing time, %.0f ms; IR %.2f s" % (onset * 1000, len(ir) / sr))
    print("     Hz      T60       Q     reverberant vs direct")
    for f, t60, ratio in bands:
        if f > sr / 2:
            continue
        qf = band_q.get(f, q) if band_q else q
        print("   %6.0f   %5.2f s  %6.2f   %+6.1f dB"
              % (f, t60, qf, 10 * math.log10(ratio)))

    wet = np.empty_like(x)
    for c in range(x.shape[1]):
        wet[:, c] = overlap_add(x[:, c], ir[:, c])
    out = x + wet
    peak = np.abs(out).max()
    print("   direct peak %.3f, with tail %.3f" % (np.abs(x).max(), peak))
    write_wav(outp, out, sr)
    print("   written")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
