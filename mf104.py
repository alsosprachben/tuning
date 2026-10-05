#!/usr/bin/env python3
"""The Moogerfooger MF-104M Analog Delay, after a Moog.

The Messenger has no delay; the echo a Moog player reaches for is Moog's own
bucket-brigade pedal, so that is what this is -- the device, from its 2012
manual (Moog Music, "moogerfooger MF-104M Analog Delay"), not an echo
invented for the purpose. It sits in the Moog's own panel (moog.PANEL, the
mf104_* knobs) beside the synth's, so it is saved with a part and in its
presets as every knob is.

WHAT THE PEDAL IS. "A dual-range Bucket Brigade Device (BBD) providing a
range of delay times from 40 milliseconds to 800 milliseconds": 40-400 ms
on SHORT, 80-800 on LONG, the time set by the clock that walks the signal
through 8192 buckets. The line's anti-alias filter must change with the
range, "the SHORT setting will yield a higher frequency response" -- about
3.0 kHz SHORT, 1.7 kHz LONG (the manual's figure 6; its text came through
garbled, so the pairing is the likely one). FEEDBACK returns the line's
output to its input; "with the control set to about 8, the echoes sustain
indefinitely", past it they self-oscillate. MIX is a crossfade, dry to wet.
The LFO modulates the delay TIME, which bends the repeats' pitch; "AMOUNT
of about 9" with the sine "gives two octaves" -- of delay time, the clock
being an exponential oscillator: the functional range of TIME shrinks as
AMOUNT grows so the line's limits hold.

AS PARTIALS. A delay is linear and the renderer's partials are a delay's
natural currency: repeat k of a partial is the same partial k*tau later,
its phase anchor turned by its own frequency times that, at a gain of
wet * fb^(k-1) * |H(f)|^k -- k trips round the line, so k times through its
filter, which is why EACH REPEAT IS DARKER THAN THE ONE BEFORE. That is the
pedal's character, and it falls out of the physics rather than being a
setting. Everything the renderer measures from a partial's own onset (its
envelope, a Moog's two contours, its release) moves with the copy; see
expand() for the phase anchors and vibrato that have to be carried.

THE LFO AS VIBRATO. y(t) = x(t - T(t)): a delay whose length moves is a
phase modulation of the delayed signal by -2 pi f dT. Repeat k has crossed
the line k times, each crossing delayed by tau(t) at its own moment, so its
deviation is the sum of k copies of the LFO a period of tau apart -- for a
sine, ONE sine, whose depth and phase are |S_k| and arg S_k with
S_k = sum_i e^{-i w i tau}. That is exactly what the kernel's vibrato
columns (vd, vr, vp) carry. The line's swing is EXPONENTIAL, tau0 2^(A sin wt)
= tau0 e^(a sin wt) with a = A ln2, which is tau0 [I0(a) + 2 I1(a) sin wt +
harmonics]: the mean delay tau0 I0(a) is the repeat's spacing, and the
fundamental 2 I1(a) is carried exactly. Its harmonics are not: measured,
1.8% of the swing at a fifth of an octave of AMOUNT and 4.5% at half,
where a linear tau0 (1 + a sin) was 7% and 16% off. Sine only: the other five waveshapes
are not one sine. And a copy carries ONE vibrato,
so with AMOUNT up the pedal's replaces the note's own (a pad's slow drift).

LEFT OUT, and said so: DRIVE's saturation; self-oscillation (FEEDBACK stops
at 0.98, the echoes' sustain, since a line that runs away needs its
saturation to settle); the brief pitch bend of audio already in the line
when TIME moves (settings are read at note-on); BBD clock noise. A channel's
pitch-bend rows and a Moog's free-running LFO 1 run on the absolute clock,
so a repeat bends and sweeps with the live note rather than the one it
repeats; a Moog's noise repeats as fresh noise of the same colour.
"""
import math

import numpy as np

GRID = 128                       # moog.MG: a repeat's delay is a whole number of
                                 # grid points, so a Moog note's pitch and shape
                                 # rows can be read by an offset, exactly
# (shortest s, longest s, anti-alias filter Hz) for SHORT and LONG
RANGES = ((0.040, 0.400, 3000.0), (0.080, 0.800, 1700.0))
FILTER_POLES = 4                 # the anti-alias low-pass's order: not in the
                                 # manual, a constant for the ear to check
FB_AT_8 = 0.98                   # FEEDBACK at "8": the echoes all but sustain
REPEAT_FLOOR = 1e-3              # a repeat under -60 dB of its NOTE's loudest
                                 # partial is dropped -- inaudible under the note.
                                 # Of its own partial (-70) kept a weak harmonic's
                                 # repeats nobody hears: a held 8-note chord at
                                 # FEEDBACK 0.5 cost 4.8 ms of a 2.67 ms block live;
                                 # here, 2.5-2.7 (4 notes: 2.0). A held chord through
                                 # a feedback line IS every repeat sounding at once.
MAX_REPEATS = 24
RATE_LO, RATE_HI = 0.05, 50.0    # LFO RATE, Hz, panel range
OCT_AT_9 = 1.0                   # AMOUNT 0.9: +-1 octave of delay time, the
                                 # manual's "two octaves" of swing

# The pedal's knobs, as moog.PANEL carries them (0..1 unless a switch)
PANEL = dict(mf104_on=False, mf104_time=0.5, mf104_range=0, mf104_feedback=0.4,
             mf104_mix=0.5, mf104_rate=0.3, mf104_amount=0.0, mf104_wave=0)
WAVES = ('sine',)                # the waveshapes modelled (see the docstring)


def _clip(v):
    return max(0.0, min(1.0, float(v)))


def knob_time(v, rng):
    """TIME: exponential across the range (the BBD's clock is an oscillator)."""
    lo, hi, _fc = RANGES[int(rng)]
    return lo * (hi / lo) ** _clip(v)


def knob_feedback(v):
    """FEEDBACK: 0 to FB_AT_8 at "8", held there past it (no self-oscillation)."""
    return FB_AT_8 * min(1.0, _clip(v) / 0.8)


def knob_rate(v):
    """LFO RATE: 0.05 to 50 Hz, exponentially."""
    return RATE_LO * (RATE_HI / RATE_LO) ** _clip(v)


def knob_amount(v):
    """LFO AMOUNT: the delay time's swing, octaves either way."""
    return OCT_AT_9 * _clip(v) / 0.9


def settings(panel):
    """The pedal's state from a Moog panel, or None when it is off (or at
    MIX 0, when nothing of it is heard)."""
    if not panel or not panel.get('mf104_on', False):
        return None
    p = dict(PANEL); p.update({k: v for k, v in panel.items() if k in PANEL})
    mix = _clip(p['mf104_mix'])
    if mix <= 0.0:
        return None
    rng = int(p['mf104_range'])
    return dict(time=knob_time(p['mf104_time'], rng), fc=RANGES[rng][2],
                fb=knob_feedback(p['mf104_feedback']), wet=mix, dry=1.0 - mix,
                rate=knob_rate(p['mf104_rate']), amount=knob_amount(p['mf104_amount']))


def bessel_i(n, x):
    """I_n(x), the modified Bessel function, by its series (x is small)."""
    return sum((x / 2.0) ** (2 * m + n) / (math.factorial(m) * math.factorial(m + n))
               for m in range(12))


def delay_samples(st, sr):
    """tau in samples -- the line's MEAN delay, tau0 I0(A ln2) when the LFO
    swings it -- a whole number of Moog grid points."""
    mean = st['time'] * bessel_i(0, st['amount'] * math.log(2.0))
    return max(GRID, int(round(mean * sr / GRID)) * GRID)


def bbd_gain(f_hz, fc):
    """|H| of the line's anti-alias low-pass, once."""
    x = abs(float(f_hz)) / fc
    return (1.0 + x * x) ** (-FILTER_POLES / 2.0)


def repeats(st, f_hz, sr, rel=1.0):
    """[(k, delay samples, gain)] for a partial at f_hz, until a repeat falls
    under REPEAT_FLOOR -- of the note's loudest partial, `rel` being this
    partial's level against that one."""
    d = delay_samples(st, sr)
    h = bbd_gain(f_hz, st['fc'])
    out = []
    for k in range(1, MAX_REPEATS + 1):
        g = st['wet'] * (st['fb'] ** (k - 1)) * h ** k
        if g * rel < REPEAT_FLOOR:
            break
        out.append((k, k * d, g))
    return out


def lfo_vibrato(st, k, sr, om, t_on):
    """Repeat k's wobble as the kernel's vibrato: (vd, vr, vp, dp0), dp0 the
    phase to add to the copy's anchors so its deviation is the line's at its
    own onset, not zero there (the kernel integrates from note-on). om is
    the partial's radians per sample, t_on the copy's onset in seconds.
    None when the LFO is off."""
    A = st['amount']
    if A <= 0.0:
        return None
    w = 2.0 * math.pi * st['rate']
    tau = delay_samples(st, sr) / float(sr)         # the crossings' spacing
    s = sum(complex(math.cos(w * i * tau), -math.sin(w * i * tau)) for i in range(k))
    # the swing's fundamental, 2 I1(a) of tau0, per crossing
    dlt = st['time'] * 2.0 * bessel_i(1, A * math.log(2.0)) * abs(s)
    th = math.atan2(s.imag, s.real)
    f = om * sr / (2.0 * math.pi)
    return (w * dlt, st['rate'], th - math.pi / 2.0,
            -2.0 * math.pi * f * dlt * math.sin(w * t_on + th))


def expand(A, notes, sr, cols, dup_fx=None, meta=None):
    """Add each pedal note's repeats to the partial table A, in place, and
    scale its dry rows by the crossfade. notes: [(first row, end row,
    settings)]. dup_fx(fx, D) gives a Moog row for a copy D samples late
    (pitch and shape rows offset), or None to keep fx. Returns (rows added,
    the latest sample any copy may still sound)."""
    if not notes:
        return 0, 0
    keys = list(cols)
    extra = {k: [] for k in keys}
    made, last = 0, 0
    tpi = 2.0 * math.pi
    for i0, i1, st in notes:
        lv = [max(abs(float(A['aL'][i])), abs(float(A['aR'][i]))) for i in range(i0, i1)]
        top = max(lv) if lv else 0.0
        for i in range(i0, i1):
            row = {k: A[k][i] for k in keys}
            om = float(row['om'])
            rel = lv[i - i0] / top if top > 0.0 else 0.0
            # the line filters what SOUNDS: the partial's own frequency, not
            # nf, which on a Moog is the key's nominal harmonic (a transposed
            # OSC 2's is not where it sounds)
            for k, d, g in repeats(st, om * sr / (2.0 * math.pi), sr, rel):
                c = dict(row)
                c['non'] = row['non'] + d
                c['noff'] = row['noff'] + d
                c['nfr'] = float(c['non']) - math.floor(float(c['non']))
                c['p0'] = row['p0'] - om * d
                c['p0R'] = row['p0R'] - om * d
                if float(row.get('fmw', 0.0)) != 0.0:
                    c['fmp'] = row['fmp'] - float(row['fmw']) * d
                    c['fmpR'] = row['fmpR'] - float(row['fmw']) * d
                if float(row.get('vd', 0.0)) != 0.0:     # the note's own vibrato, delayed
                    c['vp'] = row['vp'] - tpi * float(row['vr']) * d / sr
                vb = lfo_vibrato(st, k, sr, om, float(c['non']) / sr)
                if vb is not None:                       # ...or the line's, in its place
                    c['vd'], c['vr'], c['vp'] = vb[0], vb[1], vb[2]
                    c['vdl'] = 0.0
                    c['p0'] = c['p0'] + vb[3]
                    c['p0R'] = c['p0R'] + vb[3]
                c['aL'] = row['aL'] * g
                c['aR'] = row['aR'] * g
                c['aM'] = row['aM'] * g
                if dup_fx is not None and int(row.get('fx', -1)) >= 0:
                    nf = dup_fx(int(row['fx']), d)
                    if nf is not None:
                        c['fx'] = nf
                for kk in keys:
                    extra[kk].append(c[kk])
                if meta is not None:
                    meta.append((i, k))
                made += 1
                last = max(last, int(c['noff']) + int(math.ceil(float(row.get('re', 0.0)))))
            for kk in ('aL', 'aR', 'aM'):
                A[kk][i] = A[kk][i] * st['dry']
    for kk in keys:
        A[kk].extend(extra[kk])
    return made, last


def selftest():
    ok = True
    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print("  %-62s %s%s" % (name, "ok" if cond else "FAIL", detail))
    sr = 48000
    st = settings(dict(mf104_on=True, mf104_time=0.5, mf104_range=0,
                       mf104_feedback=0.5, mf104_mix=0.5, mf104_rate=0.3, mf104_amount=0.2))
    check("TIME spans the manual's ranges",
          abs(knob_time(0, 0) - 0.04) < 1e-12 and abs(knob_time(1, 0) - 0.4) < 1e-12
          and abs(knob_time(0, 1) - 0.08) < 1e-12 and abs(knob_time(1, 1) - 0.8) < 1e-12,
          "  (40-400 ms SHORT, 80-800 LONG)")
    rp = repeats(st, 2000.0, sr)
    hs = [g / (st['wet'] * st['fb'] ** (k - 1)) for k, _d, g in rp]
    h1 = bbd_gain(2000.0, st['fc'])
    check("repeat k is k trips through the line's filter",
          all(abs(h - h1 ** k) < 1e-12 for (k, _d, _g), h in zip(rp, hs)) and len(rp) > 2,
          "  (%d repeats of a 2 kHz partial)" % len(rp))
    lo = [g for _k, _d, g in repeats(st, 300.0, sr)]
    hi = [g for _k, _d, g in repeats(st, 4000.0, sr)]
    check("...so each repeat is darker than the one before",
          all(b / a < bl / al for (al, bl), (a, b) in zip(zip(lo, lo[1:]), zip(hi, hi[1:]))),
          "  (4 kHz falls faster than 300 Hz, repeat on repeat)")
    # the LFO: the kernel's vibrato phase against the line's own, k crossings
    w = 2 * math.pi * st['rate']
    tau = delay_samples(st, sr) / sr
    om = 2 * math.pi * 1000.0 / sr
    worst = 0.0
    for k in (1, 3):
        t_on = 1.234
        vd, vr, vp, dp0 = lfo_vibrato(st, k, sr, om, t_on)
        t = t_on + np.linspace(0.0, 2.0, 2001)
        f = 1000.0
        kern = dp0 + (f * vd / vr) * (np.cos(2 * math.pi * vr * t_on + vp) - np.cos(2 * math.pi * vr * t + vp))
        a1 = st['time'] * 2.0 * bessel_i(1, st['amount'] * math.log(2))
        lin = -2 * math.pi * f * sum(a1 * np.sin(w * (t - i * tau)) for i in range(k))
        worst = max(worst, float(np.max(np.abs(kern - lin))))
    check("the LFO's wobble is k crossings of the modulated line",
          worst < 1e-9, "  (kernel phase against the line's: %.1e rad)" % worst)
    t = np.linspace(0, 1.0 / st['rate'], 4001)
    for A, bound in ((0.2, 0.02), (0.5, 0.05)):
        a = A * math.log(2)
        ex = 2.0 ** (A * np.sin(w * t))                  # the line's own swing, over tau0
        fit = bessel_i(0, a) + 2.0 * bessel_i(1, a) * np.sin(w * t)
        err = float(np.max(np.abs(ex - fit)) / (np.max(ex) - np.min(ex)))
        check("...its fundamental carried, harmonics within the docstring's (A=%.1f)" % A,
              err < bound, "  (%.1f%% of the swing left out)" % (100 * err))
    print("  all passed" if ok else "  FAILED")
    return ok


if __name__ == '__main__':
    import sys
    sys.exit(0 if selftest() else 1)
