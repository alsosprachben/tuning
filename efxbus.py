"""A PART'S OWN BUS: the insertion effects that act on the summed waveform
and not on any one partial -- Lo-Fi's rate and bit reduction, a compressor
or limiter that follows the level, an enhancer's saturated top. A partial is
a frequency; these are nonlinear or level-dependent, so the part is rendered
to its own buffer, processed here, and added back to the mix (streamrender
and blockrender's synth_window split the window's rows for it; its reverb
send is rendered and processed alike).

Each processor is STATEFUL across windows -- the hold's phase, the filters'
memories, the envelope -- so a stream of windows is one continuous signal,
and the stream renders the part as the whole table does. Laws Roland does not
print are chosen and named (the SC-88Pro's manual gives Lo-Fi's filters and
its Type only as numbers: "the sound quality will become poorer as this value
is increased").
"""
import math

import numpy as np

# LO-FI 1: Type 1-9 onto a held sample rate and a bit depth, poorer as it
# rises; its Pre and Post Filter 1-6 onto a low-pass corner (1 none). Chosen.
LOFI_RATE = (32000, 22050, 16000, 12000, 11025, 8000, 6000, 5000, 4000)
LOFI_BITS = (14, 12, 11, 10, 9, 8, 7, 6, 5)
LOFI_FILTER_HZ = (None, 8000.0, 6000.0, 4000.0, 2500.0, 1500.0)


class OnePole:
    """A one-pole low-pass (fc None: none), its memory carried per ear."""

    def __init__(self, fc, sr):
        self.a = None if not fc else math.exp(-2.0 * math.pi * fc / sr)
        self.z = [0.0, 0.0]

    def run(self, x, ear):
        if self.a is None:
            return x
        from scipy.signal import lfilter
        # the filter's state carried from the window before (its final, as
        # lfilter's transposed form has it, is the next window's initial)
        y, zf = lfilter([1.0 - self.a], [1.0, -self.a], x, zi=[self.z[ear]])
        self.z[ear] = float(zf[0])
        return y


class LoFi:
    """Sample-and-hold to a lower rate, quantised to fewer bits, a low-pass
    before and after: the "Lo-Fi" of a cheap sampler."""

    def __init__(self, sr, lofi_type=6, pre=2, post=2, rate=None, bits=None):
        k = max(1, min(9, int(lofi_type))) - 1
        self.sr = sr
        self.step = sr / float(rate or LOFI_RATE[k])       # input samples a held sample
        self.q = 2.0 ** -((bits or LOFI_BITS[k]) - 1)       # the quantum, full scale 1
        self.pre = OnePole(LOFI_FILTER_HZ[max(1, min(6, int(pre))) - 1], sr)
        self.post = OnePole(LOFI_FILTER_HZ[max(1, min(6, int(post))) - 1], sr)
        self.phase = 0.0                                    # where the next hold starts
        self.held = [0.0, 0.0]
        self.n = 0                                          # samples processed so far

    def process(self, L, R):
        out = []
        n = len(L)
        # the hold's grid on the absolute sample clock: sample i is held from
        # the last grid point at or before it
        idx = np.arange(self.n, self.n + n, dtype=np.float64)
        k = np.floor(idx / self.step)
        start = np.ceil(k * self.step).astype(np.int64)     # the grid point's sample
        for ear, x in enumerate((L, R)):
            x = self.pre.run(np.asarray(x, np.float64), ear)
            y = np.empty(n)
            first = start - self.n                          # within this window, or before it
            inside = first >= 0
            y[inside] = x[first[inside]]
            y[~inside] = self.held[ear]
            y = np.round(y / self.q) * self.q
            if n:
                self.held[ear] = float(x[first[-1]]) if first[-1] >= 0 else self.held[ear]
            out.append(self.post.run(y, ear).astype(np.float32))
        self.n += n
        return out[0], out[1]


class Compressor:
    """A level-following gain: an envelope (attack, release) against a
    threshold, ratio above it, a makeup after. Limiter: a high ratio."""

    def __init__(self, sr, threshold_db=-20.0, ratio=4.0, attack_s=0.01, release_s=0.15, makeup_db=0.0):
        self.t, self.r = threshold_db, ratio
        self.ka = math.exp(-1.0 / max(1.0, attack_s * sr))
        self.kr = math.exp(-1.0 / max(1.0, release_s * sr))
        self.mk = 10.0 ** (makeup_db / 20.0)
        self.env = 0.0

    def process(self, L, R):
        L = np.asarray(L, np.float64); R = np.asarray(R, np.float64)
        lv = np.maximum(np.abs(L), np.abs(R))
        env = np.empty(len(lv)); e = self.env
        for i, v in enumerate(lv):                          # one pass, the state carried
            k = self.ka if v > e else self.kr
            e = k * e + (1.0 - k) * v
            env[i] = e
        self.env = e
        db = 20.0 * np.log10(np.maximum(env, 1e-9))
        over = np.maximum(db - self.t, 0.0)
        g = 10.0 ** (-over * (1.0 - 1.0 / self.r) / 20.0) * self.mk
        return (L * g).astype(np.float32), (R * g).astype(np.float32)


class Enhancer:
    """The top octaves made brighter: the signal above ENH_HZ, saturated, its
    new harmonics mixed back at Mix, Sens driving the saturation."""

    ENH_HZ = 2000.0

    def __init__(self, sr, sens=64, mix=64):
        self.hp = OnePole(self.ENH_HZ, sr)
        self.drive = 1.0 + 15.0 * sens / 127.0
        self.mix = mix / 127.0

    def process(self, L, R):
        out = []
        for ear, x in enumerate((L, R)):
            x = np.asarray(x, np.float64)
            hi = x - self.hp.run(x, ear)                    # above the corner
            sat = np.tanh(self.drive * hi) / self.drive
            out.append((x + self.mix * sat).astype(np.float32))
        return out[0], out[1]


# THE NOISES' SOURCE: noise keyed by the absolute sample -- each NOISE_CHUNK
# of samples drawn from its own seed -- so a stream of windows draws exactly
# the noise the whole table does, however the windows fall
NOISE_CHUNK = 8192


def noise(n0, n, seed, kind='normal'):
    """n samples of noise from absolute sample n0 (normal, or uniform 0..1)."""
    out = np.empty(n)
    k0, k1 = n0 // NOISE_CHUNK, (n0 + n - 1) // NOISE_CHUNK if n else n0 // NOISE_CHUNK - 1
    for k in range(k0, k1 + 1):
        r = np.random.default_rng([int(seed), int(k)])
        c = r.standard_normal(NOISE_CHUNK) if kind == 'normal' else r.random(NOISE_CHUNK)
        a, b = max(n0, k * NOISE_CHUNK), min(n0 + n, (k + 1) * NOISE_CHUNK)
        out[a - n0:b - n0] = c[a - k * NOISE_CHUNK:b - k * NOISE_CHUNK]
    return out


class Filt:
    """A filter (b, a) with its memory carried across windows, per ear."""

    def __init__(self, b, a):
        from scipy.signal import lfilter_zi
        self.b, self.a = np.asarray(b, float), np.asarray(a, float)
        self.z = [np.zeros(len(lfilter_zi(self.b, self.a))) for _ in range(2)]

    def run(self, x, ear=0):
        from scipy.signal import lfilter
        y, self.z[ear] = lfilter(self.b, self.a, x, zi=self.z[ear])
        return y


def butter(kind, hz, sr, order=2):
    from scipy.signal import butter as _b
    wn = np.minimum(np.asarray(hz, float), 0.45 * sr) / (0.5 * sr)
    return Filt(*_b(order, wn, kind))


def lowpass(hz, sr):
    """A one-pole low-pass at hz, or None (Roland's "Bypass")."""
    return None if not hz else Filt([1.0 - math.exp(-2.0 * math.pi * hz / sr)],
                                   [1.0, -math.exp(-2.0 * math.pi * hz / sr)])


# LO-FI 2: Type 1-6 onto a held rate and bits (as Lo-Fi 1's, a radio's and an
# old sampler's range); its noises' levels 0-127 onto amplitude, 127 at
# NOISE_FULL_DB rms at the output; the radio's detune fading the station
# into AM static (band 300-3000 Hz) and wandering; the record's crackle per
# Disc Type -- LP, EP, SP: clicks at a rate, a tick once a revolution (33,
# 45, 78 rpm), SP's hiss louder; RND: clicks only; the hum at 50/60 Hz with
# the buzz of its harmonics. Chosen.
LOFI2_RATE = (16000, 11025, 8000, 6000, 5000, 4000)
LOFI2_BITS = (12, 10, 8, 7, 6, 5)
# (127 at -40 dB rms at the output's scale, where one part at a firm
# velocity peaks near -25 dB: the noise under the music, not over it)
NOISE_FULL_DB = -40.0
DISC = {0: (6.0, 33.3 / 60.0, 0.15), 1: (10.0, 45.0 / 60.0, 0.2), 2: (20.0, 78.0 / 60.0, 0.5),
        3: (14.0, None, 0.1)}           # clicks a second, revolutions a second, hiss level
HUM_HARM = ((1, 1.0), (2, 0.5), (3, 0.35), (4, 0.15), (5, 0.2), (7, 0.1))
# pink from white: Paul Kellet's three-pole filter
PINK = ([0.049922035, -0.095993537, 0.050612699, -0.004408786],
        [1.0, -2.494956002, 2.017265875, -0.522189400])


class LoFi2:
    """Lo-Fi with noises: a radio's static and detune, white or pink noise, a
    record's crackle, mains hum -- each with its low-pass, heard even when the
    part is silent, mono or a stereo pair; a filter after."""

    def __init__(self, sr, lofi_type=2, fil_type=0, cutoff=630.0, detune=0, radio_nz=64,
                 pink=0, wp_lpf=None, wp_level=0, disc_type=0, disc_lpf=None, disc_level=0,
                 hum_type=0, hum_lpf=None, hum_level=0, stereo=0, pan=64):
        k = max(1, min(6, int(lofi_type))) - 1
        self.sr = sr
        self.lofi = LoFi(sr, 1, 1, 1, rate=LOFI2_RATE[k], bits=LOFI2_BITS[k])
        self.post = None if not fil_type else butter('low' if fil_type == 1 else 'high', cutoff, sr)
        full = 10.0 ** (NOISE_FULL_DB / 20.0)
        self.det = detune / 127.0
        self.radio_amp = full * radio_nz / 127.0 * self.det
        self.radio_band = butter('band', (300.0, 3000.0), sr, 1) if detune else None
        self.radio_static = butter('band', (300.0, 3000.0), sr, 1) if detune else None
        self.wp_amp = full * wp_level / 127.0
        self.pink = Filt(*PINK) if pink else None
        self.wp_lpf = lowpass(wp_lpf, sr)
        self.disc_amp = full * disc_level / 127.0
        self.disc = DISC[max(0, min(3, int(disc_type)))]
        self.disc_lpf = lowpass(disc_lpf, sr)
        self.click = Filt([1.0], [1.0, -math.exp(-1.0 / (0.0003 * sr))])
        self.hum_amp = full * hum_level / 127.0
        self.hum_hz = 60.0 if hum_type else 50.0
        self.hum_lpf = lowpass(hum_lpf, sr)
        self.stereo = bool(stereo)
        th = (max(0, min(127, int(pan))) - 64) / 63.0 * 0.25 * math.pi + 0.25 * math.pi
        self.pan = (math.cos(th), math.sin(th))
        self.n = 0

    def _noises(self, ear, n):
        """The noise generator's sum for one ear (ear 0 the mono one)."""
        sr, n0, seed = self.sr, self.n, 1000 * (ear + 1)
        y = np.zeros(n)
        if self.radio_amp:
            y += self.radio_amp * self.radio_static.run(noise(n0, n, seed + 1), ear) * 4.5
        if self.wp_amp:
            w = noise(n0, n, seed + 2)
            if self.pink is not None:
                w = self.pink.run(w, ear) * 11.0
            if self.wp_lpf is not None:
                w = self.wp_lpf.run(w, ear)
            y += self.wp_amp * w
        if self.disc_amp:
            rate, rev, hiss = self.disc
            u = noise(n0, n, seed + 3, 'uniform')
            sgn = np.sign(noise(n0, n, seed + 4))
            imp = np.where(u < rate / sr, sgn * (0.3 + 2.0 * (u * sr / rate)), 0.0)
            if rev:                                     # the tick once a revolution
                idx = np.arange(n0, n0 + n)
                imp += np.where(np.floor(idx * rev / sr) != np.floor((idx - 1) * rev / sr), 2.5, 0.0)
            d = 1.5 * self.click.run(imp, ear) + hiss * noise(n0, n, seed + 5)
            if self.disc_lpf is not None:
                d = self.disc_lpf.run(d, ear)
            y += self.disc_amp * d
        if self.hum_amp:
            t = np.arange(n0, n0 + n) / float(sr)
            h = sum(a * np.sin(2.0 * math.pi * k * self.hum_hz * t) for k, a in HUM_HARM)
            if self.hum_lpf is not None:
                h = self.hum_lpf.run(h, ear)
            y += self.hum_amp * h
        return y

    def process(self, L, R):
        n = len(L)
        L = np.asarray(L, np.float64); R = np.asarray(R, np.float64)
        if self.radio_band is not None:
            # THE RADIO OFF ITS STATION: the band of an AM set, fading and
            # wandering as the tuning drifts further (a slow, keyed wander)
            t = np.arange(self.n, self.n + n) / float(self.sr)
            fade = (1.0 - 0.8 * self.det) * (1.0 + 0.3 * self.det * np.sin(2.0 * math.pi * 0.37 * t)
                                               * np.sin(2.0 * math.pi * 0.11 * t + 1.0))
            L = self.radio_band.run(L, 0) * fade
            R = self.radio_band.run(R, 1) * fade
        yL, yR = self.lofi.process(L.astype(np.float32), R.astype(np.float32))
        yL = np.asarray(yL, np.float64); yR = np.asarray(yR, np.float64)
        if self.stereo:
            yL = yL + self._noises(0, n); yR = yR + self._noises(1, n)
        else:                                           # the effect mono, at its Pan
            m = 0.5 * (yL + yR) + self._noises(0, n)
            yL, yR = m * self.pan[0] * math.sqrt(2.0), m * self.pan[1] * math.sqrt(2.0)
        if self.post is not None:
            yL = self.post.run(yL, 0); yR = self.post.run(yR, 1)
        self.n += n
        return yL.astype(np.float32), yR.astype(np.float32)


class GateReverb:
    """A reverb cut off before its natural length -- a burst of dense
    reflections Gate Time long (the classic gated drum): Norm a flat burst,
    Reverse one that rises, Sweep1 one moving right to left, Sweep2 left to
    right (the SC-8850 manual's words). A noise impulse response, decorrelated
    per ear, its energy whole, convolved with the part (mono in) and its
    history carried across windows. The burst's shape is chosen."""

    LPF_HZ = 7000.0

    def __init__(self, sr, gtype=0, pre_ms=0.5, gate_ms=65.0):
        n = max(8, int(round(gate_ms / 1000.0 * sr)))
        pre = int(round(pre_ms / 1000.0 * sr))
        u = np.arange(n) / float(n)
        env = {1: (u + 0.05) ** 1.5}.get(gtype, np.exp(-0.7 * u))
        f = min(n, max(2, int(0.002 * sr)))
        env[-f:] *= np.linspace(1.0, 0.0, f)              # the gate's close, 2 ms
        th = 0.5 * math.pi * (u if gtype == 3 else 1.0 - u)
        side = ((np.cos(th), np.sin(th)) if gtype in (2, 3) else (np.ones(n), np.ones(n)))
        from scipy.signal import lfilter
        a = math.exp(-2.0 * math.pi * self.LPF_HZ / sr)
        self.h = []
        for ear in (0, 1):
            x = lfilter([1.0 - a], [1.0, -a], noise(0, n, 77 + ear)) * env * side[ear]
            x /= math.sqrt((x ** 2).sum()) + 1e-12
            self.h.append(np.concatenate([np.zeros(pre), x]))
        self.hist = np.zeros(len(self.h[0]) - 1)

    def process(self, L, R):
        """The part (mono in) through the pair of responses, its history
        carried: each window's output as the whole signal's would be."""
        from scipy.signal import fftconvolve
        m = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
        x = np.concatenate([self.hist, m])
        k = len(self.hist)
        out = [fftconvolve(x, h, mode='full')[k:k + len(m)] for h in self.h]
        self.hist = x[len(x) - k:] if k else self.hist
        return out[0].astype(np.float32), out[1].astype(np.float32)


# THE REVERB TYPE's LAWS (Roland prints only the names): Time 0-127 onto a
# decay (RT60) of 0.1 s * 50^(Time/127) -- 4 s at its default 120 -- times the
# type's own (Rooms 0.4, Stages 0.7, Halls 1); the reverb's highs dying faster,
# HF Damp the corner they fall to; Room2 sparse, Stage1 a slower late decay,
# Stage2 strong early reflections, Hall2 denser and longer than Hall1. Chosen.
REVERB_TYPES = {0: dict(rt=0.4, dense=1.0), 1: dict(rt=0.4, dense=0.04),
                2: dict(rt=0.7, dense=1.0, late=1.6), 3: dict(rt=0.7, dense=1.0, early=True),
                4: dict(rt=1.0, dense=1.0), 5: dict(rt=1.2, dense=1.0)}
EARLY = ((0.011, 0.9, 0.3), (0.019, -0.7, 0.8), (0.027, 0.6, 0.1), (0.041, -0.5, 0.6),
         (0.053, 0.45, 0.95), (0.071, -0.35, 0.4))   # (s, level, side 0 left..1 right)


class Reverb(GateReverb):
    """The Reverb type: a decaying noise response per ear (as GateReverb's,
    run by the same convolution), its highs damped as it decays."""

    def __init__(self, sr, rtype=0, pre_ms=74.0, time=120, damp_hz=6300.0):
        from scipy.signal import lfilter
        ty = REVERB_TYPES.get(int(rtype), REVERB_TYPES[0])
        rt = 0.1 * 50.0 ** (max(0, min(127, int(time))) / 127.0) * ty['rt']
        n = int(min(1.2 * rt, 8.0) * sr) + 8
        pre = int(round(pre_ms / 1000.0 * sr))
        t = np.arange(n) / float(sr)
        env = 10.0 ** (-3.0 * t / rt)
        if ty.get('late'):                                # a slower tail after 80 ms
            env = np.maximum(env, 0.25 * 10.0 ** (-3.0 * t / (ty['late'] * rt)))
        env *= np.minimum(1.0, t / 0.004)                 # the first reflections' build
        k = 1.0 - np.exp(-t / (rt / 3.0))                 # how far the highs have died
        a = math.exp(-2.0 * math.pi * (damp_hz or 20000.0) / sr)
        self.h = []
        for ear in (0, 1):
            x = noise(0, n, 91 + ear)
            if ty['dense'] < 1.0:                         # sparse: a few reflections
                x = np.where(noise(0, n, 93 + ear, 'uniform') < ty['dense'], x / math.sqrt(ty['dense']), 0.0)
            x = (1.0 - k) * x + k * lfilter([1.0 - a], [1.0, -a], x)
            x *= env
            if ty.get('early'):
                for ts, lv, side in EARLY:
                    x[int(ts * sr)] += lv * 30.0 * (side if ear else 1.0 - side) * math.sqrt(sr / 44100.0)
            x /= math.sqrt((x ** 2).sum()) + 1e-12
            self.h.append(np.concatenate([np.zeros(pre), x]))
        self.hist = np.zeros(len(self.h[0]) - 1)


# THE COMPRESSOR'S AND LIMITER'S LAWS where Roland prints none: Attack 0-127
# onto 1-50 ms (a slower one lets the pick through), Sustain onto a threshold
# 10 to 40 dB down at 8:1, release 150 ms; the Limiter's Threshold onto -60..0
# dB and Release onto 10 ms-1 s; Post Gain 0/+6/+12/+18 dB. Chosen.
def make(kind, sr, **kw):
    """A processor of the kind (efxbus's classes), from its spec."""
    if kind == 'lofi':
        return LoFi(sr, kw.get('lofi_type', 6), kw.get('pre', 2), kw.get('post', 2))
    if kind == 'comp':
        a = kw.get('attack', 72) / 127.0
        return Compressor(sr, threshold_db=-10.0 - 30.0 * kw.get('sustain', 100) / 127.0, ratio=8.0,
                          attack_s=0.001 + 0.049 * a, release_s=0.15,
                          makeup_db=6.0 * kw.get('post_gain', 0))
    if kind == 'limit':
        rel = 0.01 * 100.0 ** (kw.get('release', 16) / 127.0)
        return Compressor(sr, threshold_db=-60.0 * (1.0 - kw.get('threshold', 85) / 127.0),
                          ratio=(1.5, 2.0, 4.0, 100.0)[min(3, kw.get('ratio', 2))],
                          attack_s=0.001, release_s=rel, makeup_db=6.0 * kw.get('post_gain', 0))
    if kind == 'lofi2':
        return LoFi2(sr, **kw)
    if kind == 'gate':
        return GateReverb(sr, **kw)
    if kind == 'reverb':
        return Reverb(sr, **kw)
    if kind == 'enh':
        return Enhancer(sr, kw.get('sens', 64), kw.get('mix', 64))
    raise ValueError(kind)


class Bus:
    """A part's bus over the file: its processor fed the part's whole signal
    (so its state runs on), its output -- dry against effect by the type's
    Balance -- replacing the part's only inside the spans (samples) when the
    part is on the effect."""

    def __init__(self, spec, sr, gain=1.0):
        self.spec = spec
        self.proc = make(spec['kind'], sr, **spec['kw'])
        self.spans = spec['spans']
        self.dry, self.wet = spec['mix']
        # AT THE OUTPUT'S SCALE: a part's raw sum sits well under full scale
        # until the master gain, and Roland's thresholds and bits are the
        # module's output's -- so the processor hears the part as the mix will
        # be heard (gain: the master gain), and its output is taken back down
        self.gain = float(gain)

    def process(self, L, R, n0):
        L = np.asarray(L, np.float32); R = np.asarray(R, np.float32)
        yL, yR = self.proc.process(L * self.gain, R * self.gain)
        yL = (np.asarray(yL, np.float64) / self.gain).astype(np.float32)
        yR = (np.asarray(yR, np.float64) / self.gain).astype(np.float32)
        n = len(L)
        on = np.zeros(n, bool)
        for s0, s1 in self.spans:
            a, b = max(0, s0 - n0), min(n, s1 - n0)
            if b > a:
                on[a:b] = True
        oL = np.where(on, self.dry * L + self.wet * yL, L).astype(np.float32)
        oR = np.where(on, self.dry * R + self.wet * yR, R).astype(np.float32)
        return oL, oR
