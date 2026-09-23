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

  onset    the FIRST REFLECTION (the floor bounce, ~2 ms), at full strength:
           a statistical room's reverberant energy is flat from there apart
           from its decay. What changes with time is the fine structure, not
           the level -- specular arrivals at Kuttruff's reflection density
           4*pi*c^3*t^2/V, a few a second at first and hundreds by the mixing
           time (~sqrt(V) ms, 102 in the hall), each reflection turning the
           surfaces' declared scattering fraction diffuse. So the tail is a
           sparse specular train carrying (1-s)^n after n reflections, from
           the second order (blockrender draws the first), and dense noise
           carrying the rest. See build_ir. It used to fade in on a smoothstep
           nobody derived, which left the hall 32 dB short at its first
           reflection and 20 dB at 15 ms.

The first-order images do double-count slightly, since Eyring's reverberant
field includes them. Measured on this room they contribute about 2.7% of the
reverberant energy, which is -15 dB into a term that is itself an estimate.

CC91 ARRIVES HERE AS A SEND BUS, and it arrives without being asked for. A
render whose file sets CC91 leaves a `.send.wav` beside the wav and a `send`
map in the `.room.json` sidecar, and this script picks both up on its own -- so
the same command line produces a different tail depending on what the MIDI
said, which is the intent but is worth knowing when a render will not
reproduce. The send is a per-channel DISTANCE MULTIPLE against the room's
declared source distance, not a wet/dry knob: T60 has no r in it, only the
reverberant-to-direct ratio does, and it has it as r^2. So a channel sent
further does not ring longer, it rings more.

The send scales the ROOM FEED and leaves the direct sound alone. That is not
the mistake it resembles: the ratio is what a distance sets, the absolute level
is a normalisation, and holding the direct fixed is the normalisation that
makes the control a send rather than a fader. A file with CC91 at zero is
bit-identical to a file with no CC91 at all.

Merging stems: `examples/lib.py`'s `merge_room` carries the send map through,
and warns if the stems disagree, because a summed mix has no channels left to
weight and can only carry one distance.

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

    # THE DIFFUSE FIELD STARTS AT THE FIRST SCATTERING EVENT, NOT AT THE
    # MIXING TIME. Waiting for sqrt(V) ms leaves the early window holding only
    # the handful of specular images, and those comb: six coherent copies of a
    # held organ note swing the steady-state response from -43.6 dB to +8.7 dB,
    # with 43 notches below -6 dB and one at 326 Hz reaching -42.5 dB. A real
    # room does not, because it has hundreds of early reflections filling each
    # other's nulls. Starting at 10 ms left every note's ATTACK heard through
    # the unfilled comb -- audible as colouration on transients even though the
    # sustained response measured flat. So the tail begins at the FIRST
    # reflection, the floor bounce, computed from the (staggered) room.
    #
    # AND AT FULL STRENGTH, WHICH IT WAS NOT. The build used to be a smoothstep
    # from there to the mixing time, a shape nobody derived, and it left the
    # window where a hall's side reflections live 15 dB short at 15 ms and
    # 7 dB at 30 ms (hall), 18 and 9 (church). The reverberant energy of a
    # statistical room is flat from the first reflection, apart from its decay:
    # arrivals come faster as t^2 and each is weaker as 1/t^2, and the two
    # cancel. That is the envelope now.
    #
    # WHAT CHANGES WITH TIME IS THE FINE STRUCTURE, not the level. Specular
    # arrivals come at Kuttruff's reflection density 4*pi*c^3*t^2/V -- a few a
    # second at 10 ms in the hall, ~500 at 100 ms -- and each reflection turns a
    # fraction s of what it carries diffuse (SURFACE_SCATTER, per surface per
    # octave). After n reflections, n ~ c*t over the mean free path 4V/S, the
    # specular share is (1-s)^n. So the tail is two fields summed in energy:
    # a SPARSE train at the reflection density carrying (1-s)^n, and dense
    # noise carrying the rest. The specular train starts at the SECOND order,
    # because blockrender already draws the first geometrically, per partial.
    # With s = 0.3-0.5 the field is mostly diffuse within a few reflections,
    # which is why it does not crackle -- a sparse train at image density
    # alone would, each of its few arrivals carrying far too much energy.
    c = 343.0
    t0 = first_reflection(props)
    r = props.radiation_distance
    tau = t + r / c                              # time since emission
    mfp = 4.0 * volume / max(sum(room_of(props)[1].values()), 1e-6)
    order = c * tau / mfp                        # reflections so far
    gate = (t >= t0).astype(float)
    # The sparse train: arrivals at the reflection density, each scaled so the
    # train's local mean square is 1 whatever the density -- its level is the
    # envelope's job, its sparseness is the density's.
    lam = 4.0 * math.pi * c ** 3 * tau * tau / volume
    p_arr = np.clip(lam / float(sr), 0.0, 1.0)
    amp = np.sqrt(1.0 / np.maximum(p_arr, 1e-12))

    rng = np.random.RandomState(seed)
    ir = np.zeros((n, channels))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    # Where the modal field takes over, the statistical one must stand down, or
    # the same energy is delivered twice. Complementary to modal_ir's roll-off.
    fs_hz = schroeder(props)
    hp = np.clip((freqs - fs_hz) / max(fs_hz, 1e-6), 0.0, 1.0)
    for ci in range(channels):
        noise = rng.randn(n)
        spec = np.fft.rfft(noise)
        sparse = np.where(rng.rand(n) < p_arr, amp * np.sign(rng.randn(n)), 0.0)
        sparse[order < 2.0] = 0.0                  # first order is geometric
        sspec = np.fft.rfft(sparse)
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
            spar = np.fft.irfft(np.where(mask, sspec, 0.0), n)
            # Each part to unit mean square in the band, so the mix below is a
            # mix of ENERGIES: (1-s)^n specular, the rest diffuse.
            band /= math.sqrt(max(float(np.mean(band * band)), 1e-30))
            ms = float(np.mean(spar * spar))
            spar = spar / math.sqrt(ms) if ms > 0.0 else spar
            spec_share = (1.0 - scatter_at(props, fc)) ** order
            spec_share[order < 2.0] = 0.0
            band = np.sqrt(1.0 - spec_share) * band + np.sqrt(spec_share) * spar
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
    if fs_hz > 25.0:
        # ZERO-PADDED, so the high-pass is a linear filter and not a circular
        # one. Unpadded, its ringing from the START of the IR wrapped round to
        # the END -- harmless while the tail faded in from nothing, and +22 dB
        # of climb at 3.4 s in the chapel once the early field arrived at full
        # strength (roomcheck's "wrap", which is what it is for).
        f2 = np.fft.rfftfreq(2 * n, 1.0 / sr)
        hp2 = np.clip((f2 - fs_hz) / max(fs_hz, 1e-6), 0.0, 1.0)
        spec = np.fft.rfft(ir, 2 * n, axis=0) * hp2[:, None]
        ir = np.fft.irfft(spec, 2 * n, axis=0)[:n]
    return ir, bands, onset


def first_reflection(props):
    """Seconds after the direct sound at which the first reflection arrives:
    the earliest first-order image on the centre line, the floor's in every
    room here. The diffuse field begins with the first scattering event."""
    S = type(props)
    planes = [S.room_left, S.room_right, S.room_back, S.room_front, S.room_ceiling]
    r = props.radiation_distance
    arr = T._room_arrivals(planes, S.room_floor, 0.0, r, 0.0)
    return max(0.0, (min(arr) - r) / 343.0)


def scatter_at(props, f):
    """The room's area-weighted scattering coefficient at `f`."""
    _, areas = room_of(props)
    tot = sum(areas.values())
    return sum(a * props._octave_interp(props.SURFACE_SCATTER[s], f)
               for s, a in areas.items()) / max(tot, 1e-9)


def schroeder(props):
    """Below this the room rings as discrete modes; above it, statistically."""
    volume, _ = room_of(props)
    t60 = decay_and_level(props, 1.0)[3][1]      # the 500 Hz band
    return 2000.0 * math.sqrt(t60 / volume)


def modal_ir(props, sr, source_x=0.0, source_z=0.0, channels=2):
    """The room's discrete low-frequency modes, as a sum of decaying cosines.

    A rigid shoebox rings at f(nx,ny,nz) = (c/2)*sqrt((nx/Lx)^2 + (ny/Ly)^2 +
    (nz/Lz)^2), and how strongly each mode is driven and heard depends on where
    the source and the listener stand in its standing-wave pattern -- a source
    at a pressure node cannot excite that mode at all, and a listener at one
    cannot hear it. That is why bass in a small room depends so violently on
    where you sit, and why no statistical model can produce the effect.

    It matters only below the Schroeder frequency. Above that the modes overlap
    so heavily that the response is statistical, which the diffuse tail already
    describes: this hall has 1291 modes below 100 Hz with fiftyfold overlap. So
    this enumerates only up to twice Schroeder and fades out across it, and in a
    concert hall -- Schroeder 23 Hz -- it correctly does almost nothing.
    """
    lx = props.room_left + props.room_right
    ly = props.room_front + props.room_back
    lz = props.room_ceiling + props.room_floor
    # Both positions measured from one corner.
    lis = (props.room_left, props.room_back, props.room_floor)
    src = (props.room_left + source_x,
           props.room_back + props.radiation_distance,
           props.room_floor + source_z)
    fs = schroeder(props)
    fmax = min(2.0 * fs, sr / 2.0)
    c = props.sound_speed
    bands = decay_and_level(props, 1.0)

    def t60_at(f):
        best = min(bands, key=lambda b: abs(math.log(max(f, 1e-3) / b[0])))
        return best[1]

    nmax = lambda L: int(2.0 * fmax * L / c) + 1
    modes = []
    for nx in range(nmax(lx) + 1):
        for ny in range(nmax(ly) + 1):
            for nz in range(nmax(lz) + 1):
                if nx == ny == nz == 0:
                    continue
                f = 0.5 * c * math.sqrt((nx / lx) ** 2 + (ny / ly) ** 2 + (nz / lz) ** 2)
                if f > fmax or f < 1.0:
                    continue
                # cos(n*pi*x/L): the standing-wave shape, at each end of the path
                a = 1.0
                for n, L, ps, pl in ((nx, lx, src[0], lis[0]),
                                     (ny, ly, src[1], lis[1]),
                                     (nz, lz, src[2], lis[2])):
                    a *= (math.cos(n * math.pi * ps / L)
                          * math.cos(n * math.pi * pl / L))
                if abs(a) < 1e-4:
                    continue
                # FADE OUT ACROSS SCHROEDER, where the statistical tail takes
                # over -- applied to the mode's AMPLITUDE here, as it is built,
                # rather than by multiplying the finished spectrum by a mask.
                #
                # Every mode is a single cosine, so scaling its amplitude by
                # roll(f) is exactly what a magnitude mask does, and it cannot
                # wrap. Multiplying the spectrum of a 2.9 s buffer by a mask
                # with a corner in it is a CIRCULAR convolution, and it folded a
                # copy of the whole modal response back to the end of the
                # buffer. Measured on one click in the chapel: a burst 42 dB
                # above the decay it interrupted, 2.75 s late -- the buffer
                # length. Ben heard it as "an echo a couple seconds later, like
                # when listening to a taped recording... about 3 beats or 1
                # measure offset", and it reached every render of a room that
                # rings (chamber, chapel), though not the hall or church, where
                # the modes are below Schroeder and never applied.
                a *= min(1.0, max(0.0, (2.0 * fs - f) / max(fs, 1e-6)))
                if abs(a) < 1e-4:
                    continue
                modes.append((f, a, t60_at(f)))
    if not modes:
        return np.zeros((1, channels)), 0, fs

    longest = max(m[2] for m in modes)
    n = int(min(longest * 1.2, 8.0) * sr)
    t = np.arange(n) / float(sr)
    ir = np.zeros((n, channels))
    for f, a, t60 in modes:
        env = a * np.exp(-6.907755 * t / max(t60, 1e-3))
        for ci in range(channels):
            # A half-wavelength apart at these frequencies is nothing, so the
            # two ears see the same modal field -- correct, and audibly so:
            # room bass is mono.
            ir[:, ci] += env * np.cos(2.0 * math.pi * f * t)
    # The spectrum is MEASURED below, never multiplied: reading it is free of
    # the wrap that shaping it caused.
    spec = np.fft.rfft(ir, axis=0)
    fr = np.fft.rfftfreq(n, 1.0 / sr)

    # LEVEL. Summing 162 undamped mode shapes gives an impulse response 60 dB
    # too hot, and nothing in the modal arithmetic sets a scale -- the same trap
    # as the octave bands, and caught the same way. But the level is not free to
    # choose: the modal and statistical descriptions are of ONE room, so where
    # they meet they must agree. Normalise the modal field to the reverberant
    # ratio the room constant already specifies at these frequencies, by
    # mean-square gain in the band rather than by total energy.
    band = fr <= 2.0 * fs
    if band.any():
        target = decay_and_level(props, 1.0)[0][2]
        power = float((np.abs(spec[band, :]) ** 2).mean())
        if power > 0.0:
            # No 1/sqrt(n): convolution multiplies the spectrum by H, so the
            # mean of |H|^2 across the band IS the mean-square gain. Including
            # it put the modal field 47.6 dB down, which is exactly
            # 20*log10(sqrt(n)) for this length -- the sort of error that hides
            # as "the bass is a bit shy" if it is not measured.
            # Applied to the TIME-DOMAIN ir. A scalar gain cannot wrap,
            # where an inverse transform of a shaped spectrum can.
            ir = ir * math.sqrt(target / power)
    return ir, len(modes), fs


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
    # The WHOLE linear convolution, len(x) + len(h) - 1. Truncating to len(x)
    # here guillotined the reverberation at the last sample of the music: a
    # 2.44 s chapel got whatever was left of the file, which for Vivaldi's
    # Summer was 1.0 s, so the tail stopped dead around -40 dB instead of
    # decaying away. Ben: "This version is cut off." The caller decides how
    # much of it to keep.
    return out


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
    elif sw == 3:
        # 24-bit packed, three bytes little-endian per sample. Widened to int32
        # by placing the three bytes in the HIGH end and sign-extending, which
        # costs nothing and avoids an explicit sign test. Reference recordings
        # arrive this way -- the VCSL harpsichords are 24/48 -- and refusing
        # them here sent every caller off to shell out to sox instead.
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.uint32)
        v = (b[:, 0] << 8) | (b[:, 1] << 16) | (b[:, 2] << 24)
        a = v.astype(np.int32).astype(np.float64) / 2147483647.0
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
    side_send = None
    side = os.path.splitext(inp)[0] + '.room.json'
    if os.path.exists(side):
        import json
        d = json.load(open(side))
        band_q = {b['hz']: b['q'] for b in d['bands'] if b.get('energy', 0) > 0}
        print("   directivity factor from %s" % os.path.basename(side))
        _sd = d.get('send') or {}
        if _sd and len(set(_sd.values())) == 1:
            side_send = float(next(iter(_sd.values())))
    ir, bands, onset = build_ir(props, sr, q=q, seed=seed,
                                channels=x.shape[1], band_q=band_q)

    volume, areas = room_of(props)
    print("== %s -> %s" % (inp, outp))
    print("   hall %.0f m3, %.0f m2 of surface, sources at %.0f m, Q=%.1f"
          % (volume, sum(areas.values()), props.radiation_distance, q))
    print("   tail from the first reflection, %.1f ms, diffuse by the mixing time, %.0f ms; IR %.2f s"
          % (first_reflection(props) * 1000, onset * 1000, len(ir) / sr))
    print("     Hz      T60       Q     reverberant vs direct")
    for f, t60, ratio in bands:
        if f > sr / 2:
            continue
        qf = band_q.get(f, q) if band_q else q
        print("   %6.0f   %5.2f s  %6.2f   %+6.1f dB"
              % (f, t60, qf, 10 * math.log10(ratio)))

    # The modal region, where the room rings rather than diffuses. In a hall
    # this is entirely below hearing and costs nothing; in a small room it is
    # the bass. Built BEFORE the mix is allocated, because how far the room
    # rings on is part of how long the file has to be.
    mir, nmodes, fs = modal_ir(props, sr, channels=x.shape[1])
    if '--no-modes' in argv:
        print("   modes suppressed (--no-modes)")
        nmodes = 0
    use_modes = bool(nmodes) and fs > 25.0

    # ROOM FOR THE ROOM. A piece does not stop when its last note does -- the
    # hall keeps going, and that decay is the whole point of modelling one. So
    # the output is the music plus however long the room takes to fall silent,
    # rather than the length of the MIDI file.
    ring = len(ir) - 1
    if use_modes:
        ring = max(ring, len(mir) - 1)
    out = np.zeros((len(x) + ring, x.shape[1]))
    out[:len(x)] = x
    # WHAT FEEDS THE ROOM IS NOT ALWAYS WHAT REACHES THE EARS. CC91 puts each
    # channel at its own distance, and the reverberant field a source raises
    # goes as that distance while the direct sound does not move -- so the send
    # is a separate bus. Because the IR's SHAPE does not depend on distance and
    # only its amplitude does, one convolution still serves every channel: the
    # weighting happens before the sum, not after it.
    #
    # blockrender writes the bus only when the channels differ. A uniform send
    # -- including the usual case of no CC91 at all -- is a scalar on the mix,
    # so there is nothing extra to read and nothing extra to render.
    wet_in = x
    send = os.path.splitext(inp)[0] + '.send.wav'
    if os.path.exists(send):
        wet_in, _sr = read_wav(send)
        if len(wet_in) < len(x):
            wet_in = np.pad(wet_in, ((0, len(x) - len(wet_in)), (0, 0)))
        wet_in = wet_in[:len(x)]
        print("   reverb send bus from %s" % os.path.basename(send))
    elif side_send is not None and side_send != 1.0:
        wet_in = x * side_send
        print("   reverb send %.2f of nominal distance (CC91)" % side_send)
    for c in range(x.shape[1]):
        y = overlap_add(wet_in[:, c], ir[:, c])
        out[:len(y), c] += y

    if use_modes:
        print("   %d modes below %.0f Hz (Schroeder %.1f Hz) -- the room rings"
              % (nmodes, 2 * fs, fs))
        for c in range(x.shape[1]):
            y = overlap_add(x[:, c], mir[:, c])
            out[:len(y), c] += y
    elif nmodes:
        print("   %d modes, all below %.0f Hz (Schroeder %.1f Hz) -- inaudible,"
              " the field is statistical here" % (nmodes, 2 * fs, fs))
    print("   music %.2f s + %.2f s of room = %.2f s"
          % (len(x) / sr, ring / sr, len(out) / sr))
    peak = np.abs(out).max()
    print("   direct peak %.3f, with tail %.3f" % (np.abs(x).max(), peak))
    # A church puts its reverberant field 14 dB over the direct sound, so a
    # render mixed to sit near full scale has nowhere to put the room. Scale
    # rather than clip: clipping here is destructive and would be heard as the
    # model distorting, when it is only the file running out of numbers.
    if peak > 1.0:
        out = out / peak * 0.999
        print("   scaled by %.2f dB to fit; render %.1f dB quieter to keep the"
              " headroom in the mix instead" % (-20 * math.log10(peak), 20 * math.log10(peak)))
    write_wav(outp, out, sr)
    print("   written")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
