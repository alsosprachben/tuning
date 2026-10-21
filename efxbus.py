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
