"""A FILTER THAT MOVES: the insertion effects whose response sweeps over time
(gsefx -- Phaser, Auto Wah, the guitar multis' wah, Step Flanger, Humanizer),
as each partial's gain at its own frequency.

A partial is one frequency, so a filter on it is one number: |H(f)| at its
frequency, with the filter wherever the sweep has it. The kernel already
swings a row's level on the Moog's 128-sample grid for the Leslie
(synthkernel.c leslie_grid / leslie_samples); filter_grid multiplies the
same per-row gain by the filter's |H| at each grid point, from a per-channel
CONTROL TABLE (a cutoff, a delay, a formant's centre over the whole file,
built here as leslie.angle_table builds the rotors' angles) and the row's
own type and parameters. Built only into the Leslie's kernel (synth_voice_
lobe) and the GPU's block setup: a file with neither renders as it did.

Types (the kernel's `ty`):
  1 PHASER    |(1 - mix) + mix z / (1 - r z)|, z = e^{-i 2N atan(f / fc)}: N
              first-order all-passes at the swept corner fc, r its resonance
  2 LPF / 3 BPF   a resonant two-pole at the swept fc, Q its peak; mix
  4 COMB      |(1 - mix) + mix z / (1 - fb z)|, z = e^{-i 2 pi f tau}: the
              flanger's line at the swept delay tau (stepped, Step Flanger's)
  5 VOWEL     floor + three formants at the swept centres (three rows)

and a voice's own: the trumpet's PLUNGER (plunger(), type 2 driven by the
channel's aftertouch; blockrender, a voice with `plunger` set).
"""
import math

import numpy as np

# THE ROW'S COLUMNS: its control row (-1: no filter), its type and three
# parameters (by type, above), and the most it lifts any frequency (fmx: for
# the GPU's retirement, which bounds a row's level -- a resonance can peak)
FILTER_COLS = (('fsr', 'i4', -1), ('fty', 'i4', 0), ('fpa', 'f4', 0.0), ('fpb', 'f4', 0.0),
               ('fpc', 'f4', 0.0), ('fmx', 'f4', 1.0))

PHASER_STAGES = 4            # the all-passes in a phaser: four, a common pedal's; chosen
WAH_HZ = (200.0, 4000.0)     # a wah's Manual 0-127 across these, logarithmically; chosen
WAH_Q = (0.7, 12.0)          # ...and its Peak 0-127 across these Q; chosen
VOWEL_FLOOR = 0.15           # the Humanizer's floor between its formants; chosen
# the five vowels' first three formants, Hz -- a, i, u, e, o (Peterson & Barney's
# male averages, as vowels.VOWELS has them)
VOWEL_F = {0: (730, 1090, 2440), 1: (270, 2290, 3010), 2: (300, 870, 2240),
           3: (530, 1840, 2480), 4: (570, 840, 2410)}


def wah_hz(v):
    lo, hi = WAH_HZ
    return lo * (hi / lo) ** (max(0, min(127, int(v))) / 127.0)


def wah_q(v):
    lo, hi = WAH_Q
    return lo * (hi / lo) ** (max(0, min(127, int(v))) / 127.0)


def response(ty, f, ctrl, pa, pb, pc):
    """|H| at frequency f for control value(s) ctrl -- the kernel's filter_grid,
    in numpy (the peak bound, the checks)."""
    f = np.asarray(f, float)
    if ty == 1:
        z = np.exp(-1j * 2.0 * pc * np.arctan(f / np.maximum(ctrl, 1.0)))
        return np.abs((1.0 - pa) + pa * z / (1.0 - pb * z))
    if ty in (2, 3):
        x = f / np.maximum(ctrl, 1.0)
        q = max(pa, 0.1)
        den = np.sqrt((1.0 - x * x) ** 2 + (x / q) ** 2)
        w = 1.0 / den if ty == 2 else (x / q) / den
        return (1.0 - pb) + pb * w
    if ty == 4:
        z = np.exp(-1j * 2.0 * math.pi * f * ctrl)
        return np.abs((1.0 - pa) + pa * z / (1.0 - pb * z))
    if ty == 5:
        F = np.asarray(ctrl, float).reshape(3, -1)
        h = pa
        for k, (B, A) in enumerate(((80.0, 1.0), (110.0, 0.7), (160.0, 0.5))):
            u = (f - F[k]) / (0.5 * B)
            h = h + A / (1.0 + u * u)
        return h * pb
    return np.ones_like(f)


def peak(ty, pa, pb, pc):
    """The most the filter lifts any frequency (bounds the row for the GPU's
    retirement): its response's maximum over the audible range and the sweep."""
    f = np.geomspace(20.0, 20000.0, 400)
    if ty == 1:
        return float(max(1.0, (1.0 - pa) + pa / max(1e-3, 1.0 - abs(pb))))
    if ty in (2, 3):
        return float(max(1.0, (1.0 - pb) + pb * max(pa, 1.0)))
    if ty == 4:
        return float(max(1.0, (1.0 - pa) + pa / max(1e-3, 1.0 - abs(pb))))
    if ty == 5:
        return float(max(1.0, pb * (pa + 1.0 + 0.7 + 0.5)))
    return 1.0


class Channel:
    """One part's moving filter: its type, its parameters, and its control
    as a function of time (seconds) -- a list of rows for VOWEL's three."""

    def __init__(self, ty, pa, pb, pc, control, rows=1):
        self.ty, self.pa, self.pb, self.pc = ty, pa, pb, pc
        self.control = control          # t (array, s) -> array, or list of `rows` arrays
        self.rows = rows
        self.fmx = peak(ty, pa, pb, pc)


def table(channels, n_samples, sr, grid):
    """(FCT [rows, points] float32, {channel: its first row}): every channel's
    control at every grid point -- the kernel's table, in channels' order."""
    lgn = n_samples // grid + 2
    t = np.arange(lgn, dtype=np.float64) * (grid / float(sr))
    rows, first = [], {}
    for ch, c in channels.items():
        first[ch] = len(rows)
        v = c.control(t)
        rows.extend([np.asarray(x, np.float32) for x in (v if c.rows > 1 else [v])])
    out = np.ones((max(1, len(rows)), lgn), np.float32)
    for i, r in enumerate(rows):
        out[i] = r
    return out, first


def columns(mch, channels):
    """The FILTER_COLS for rows of these channels (mch: each row's channel),
    every other row on no filter. The control rows are table()'s."""
    mch = np.asarray(mch)
    n = len(mch)
    out = {k: np.full(n, v, dt) for k, dt, v in FILTER_COLS}
    row = 0
    for ch, c in channels.items():
        m = mch == ch
        if m.any():
            out['fsr'][m] = row
            out['fty'][m] = c.ty
            out['fpa'][m], out['fpb'][m], out['fpc'][m] = c.pa, c.pb, c.pc
            out['fmx'][m] = c.fmx
        row += c.rows
    return out


# THE PLUNGER (a trumpet's rubber cup over the bell, the hand opening and
# closing it -- the doo-wah): no measurement of one to fit (the one report
# that recorded it open and closed did not analyse it), so the acoustics: an
# EXTERNAL mute takes the highs, which leave along the bell's axis, and the
# hand works a wide range but plays mostly in its middle -- part-open, the
# doo-wah between -- reaching the seal and the open bell only at the ends.
# So the control's middle spans the band about PLUNGER_MID_HZ (near the open
# horn's own brightness), a share PLUNGER_LINEAR of the octaves each way
# moving evenly and the rest as the cube, steep toward PLUNGER_CLOSED_HZ
# sealed and PLUNGER_OPEN_HZ open (Ben: an even log sweep read as a phaser,
# and the plunge lives in the centre). The moving low-pass (type 2), a mild
# resonance of PLUNGER_Q -- a swept peak through every harmonic is the phaser
# -- PLUNGER_MIX of it (the rest the floor the gap leaves). Its control: the
# channel's AFTERTOUCH, how far the hand lifts -- pressure opens it, as
# pressure brightens our other brass -- held between messages and gliding at
# the hand's PLUNGER_GLIDE_S. Chosen, for Ben's ear.
PLUNGER_CLOSED_HZ = 600.0
PLUNGER_MID_HZ = 1500.0
PLUNGER_OPEN_HZ = 9000.0
PLUNGER_LINEAR = 0.3
PLUNGER_Q = 1.3
PLUNGER_MIX = 0.97
PLUNGER_GLIDE_S = 0.03


def plunger(pressure, closed_hz=PLUNGER_CLOSED_HZ, mid_hz=PLUNGER_MID_HZ, open_hz=PLUNGER_OPEN_HZ,
            linear=PLUNGER_LINEAR, q=PLUNGER_Q, mix=PLUNGER_MIX, glide=PLUNGER_GLIDE_S):
    """A plunger's moving filter (Channel) from a channel's [(t, aftertouch 0-127)]:
    sealed at 0, mid_hz at 64, open at 127."""
    ev = sorted(pressure or ())
    st = steps([0.0] + [t for t, _v in ev], [0.0] + [float(v) for _t, v in ev], glide=glide)

    def corner(t):
        u = 2.0 * np.clip(st(t), 0.0, 127.0) / 127.0 - 1.0
        g = linear * u + (1.0 - linear) * u ** 3
        return mid_hz * np.where(g < 0.0, closed_hz / mid_hz, open_hz / mid_hz) ** np.abs(g)
    return Channel(2, q, mix, 0.0, corner)


def lfo(rate, phase=0.0):
    """A free-running sine, -1..1, on the absolute clock (t in seconds)."""
    return lambda t: np.sin(2.0 * math.pi * rate * np.asarray(t, float) + phase)


def steps(times, values, glide=0.0):
    """A parameter over the file from (time, value) changes, held between --
    or, with glide (seconds), moving toward each new value at that time
    constant (the Humanizer's Accel)."""
    times = np.asarray(times, float)
    values = np.asarray(values, float)

    def at(t):
        t = np.asarray(t, float)
        i = np.clip(np.searchsorted(times, t, side='right') - 1, 0, len(values) - 1)
        if glide <= 0.0 or len(values) < 2:
            return values[i]
        prev = values[np.maximum(i - 1, 0)]
        k = np.exp(-np.maximum(t - times[i], 0.0) / glide)
        return values[i] + (prev - values[i]) * np.where(i > 0, k, 0.0)
    return at
