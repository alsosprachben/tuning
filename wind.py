"""The organ's wind: one pressure per division, shared by every pipe on its chest.

A pipe organ's pipes stand on a windchest fed by a bellows, and they all
hear its pressure. Three things move it:

  w(t)  THE WANDER. The blower and the regulator never hold perfectly still.
        Filtered noise, slow (under a hertz). How much is bounded by Pitea
        (examples/organ_wind_measure.py, sources.md): a C4 principal there
        wanders 0.47 cents in all, and its partials' level wobbles are
        UNCORRELATED -- the jet's turbulence, which the skirts already make
        (phase 2). Pressure moves every partial together, so what is shared
        must sit under that: 0.3% RMS is 0.2 cents on a flue. (Abel, Ahnert and
        Bergweiler's 3.75% RMS at a pipe foot includes the foot's own
        turbulence, which is not the chest's.)

  s(t)  THE SAG. Every speaking pipe draws wind, and a bellows is a mass on
        a spring of air: a chord's sudden demand dips the pressure, which
        overshoots and settles a little below where it was -- the "breathing"
        of a flexible wind. A damped second-order system driven by the demand,
        its natural frequency and damping set by ear (no measurement of a
        chest's sag under a chord turned up). A pipe's draw goes as its
        windway, roughly as its diameter: (f / 261.6 Hz)^-0.75, an 8'
        principal's middle C being one unit.

  trem  THE TREMULANT, a stop: a valve or beater that pulses the wind. A
        sinusoid at rate_hz, depth (fraction of the static pressure) building
        in over a quarter second when drawn and dying away when put in. Colin
        Pykett ("Tremulant Simulation in Digital Organs") gives up to 75%
        peak to peak, a church organ's fluework +-30 mm about 80 mm wg; a
        gentle tremulant is far less, and the default here is +-10%.

A pipe answers the pressure p (1 = static) as frequency p**a and amplitude
p**b. Pykett's stopped pipe, f = 0.0829 p + 170.2 Hz about p = 80 mm wg, is
a = 0.0375: 10% more wind is 6.5 cents sharp. A reed's pitch is held by its
tongue and hardly moves; its level moves more. The exponents are per family
(tonelib: wind_pitch_exp, wind_level_exp).

Everything here is computed per BLOCK of the renderer, in order, with its
state carried: so a file render (the whole piece at once) and live (a
callback at a time) run the same arithmetic.
"""
import math

import numpy as np

UNIT_HZ = 261.6             # a pipe's draw is one unit at an 8' middle C
DRAW_EXP = -0.75            # ... and goes as (f / UNIT_HZ)**DRAW_EXP


def pipe_draw(f):
    """The wind a pipe sounding f Hz draws, in units of an 8' middle C."""
    return (max(f, 8.0) / UNIT_HZ) ** DRAW_EXP


class Wind:
    """One chest's pressure, block by block.

    props: the organ's class (its wind_* attributes). blk_s: a block's length
    in seconds. seed: the wander's noise (one per division). scale: the
    shared wind's strength (TUNING_WIND), 0 = none -- the Tremulant, a stop,
    is not scaled by it.
    """
    SUB = 8                 # pressure points per block, for the pitch's mean

    def __init__(self, props, blk_s, seed=0, scale=1.0):
        self.blk_s = float(blk_s)
        self.scale = float(scale)
        self.wander_rms = float(getattr(props, 'wind_wander_rms', 0.0)) * self.scale
        self.wander_hz = float(getattr(props, 'wind_wander_hz', 0.5))
        self.sag_per_unit = float(getattr(props, 'wind_sag_per_unit', 0.0)) * self.scale
        self.sag_hz = float(getattr(props, 'wind_sag_hz', 4.0))
        self.sag_zeta = float(getattr(props, 'wind_sag_zeta', 0.35))
        self.trem_hz = float(getattr(props, 'tremulant_hz', 5.6))
        self.trem_depth = float(getattr(props, 'tremulant_depth', 0.10))
        self.trem_tau = float(getattr(props, 'tremulant_tau', 0.25))
        self.rng = np.random.default_rng(0x5EED + int(seed))
        # the wander: white noise per block through two one-poles, its gain
        # normalised so that its RMS is wander_rms
        self.wa = math.exp(-2.0 * math.pi * self.wander_hz * self.blk_s)
        self.w1 = self.w2 = 0.0
        ir = np.empty(20000)
        x1 = x2 = 0.0
        for i in range(ir.size):
            x1 = self.wa * x1 + (1.0 - self.wa) * (1.0 if i == 0 else 0.0)
            x2 = self.wa * x2 + (1.0 - self.wa) * x1
            ir[i] = x2
        self.wgain = 1.0 / math.sqrt(float(np.sum(ir * ir)))
        # the sag: a resonant two-pole at sag_hz, damping sag_zeta, unity DC
        # gain (so a held demand settles to sag_per_unit times itself)
        w = 2.0 * math.pi * self.sag_hz * self.blk_s
        r = math.exp(-self.sag_zeta * w)
        th = w * math.sqrt(max(1e-9, 1.0 - self.sag_zeta ** 2))
        self.c1, self.c2 = 2.0 * r * math.cos(th), -r * r
        self.g = 1.0 - self.c1 - self.c2
        self.s1 = self.s2 = 0.0
        self.d1 = 0.0
        # the tremulant: its depth envelope and the beater's phase
        self.te = 0.0
        self.tph = 0.0
        self.tdecay = math.exp(-self.blk_s / max(1e-6, self.trem_tau))
        self.was_on = False

    def blocks(self, demand, trem):
        """Pressure for len(demand) blocks: (n, SUB + 1) points, each block's
        evenly spaced across it from its start to its end -- which is the next
        block's start, exactly: every term is interpolated from one block edge
        to the next, so the level a block ends on is the level the next begins
        on, in a file and in live alike. demand: the units of draw speaking in
        each block. trem: the Tremulant's draw (0/1) per block."""
        n = len(demand)
        out = np.empty((n, self.SUB + 1))
        frac = np.arange(self.SUB + 1) / float(self.SUB)
        noise = self.rng.standard_normal(n) if self.wander_rms > 0.0 else None
        for b in range(n):
            # the wander: slow, its value carried edge to edge
            w0 = self.w2
            if noise is not None:
                self.w1 = self.wa * self.w1 + (1.0 - self.wa) * noise[b]
                self.w2 = self.wa * self.w2 + (1.0 - self.wa) * self.w1
            wv = (w0 + (self.w2 - w0) * frac) * (self.wgain * self.wander_rms)
            # the sag, likewise
            s0 = self.s1
            if self.sag_per_unit > 0.0:
                s = self.c1 * self.s1 + self.c2 * self.s2 + self.g * self.d1
                self.s2, self.s1 = self.s1, s
                self.d1 = float(demand[b]) * self.sag_per_unit
            sv = s0 + (self.s1 - s0) * frac
            # the tremulant: the beater restarts when the stop is drawn
            on = trem[b] >= 0.5
            if on and not self.was_on and self.te < 1e-4:
                self.tph = 0.0
            self.was_on = on
            tgt = 1.0 if on else 0.0
            e0 = self.te
            self.te = tgt + (self.te - tgt) * self.tdecay
            if not on and self.te < 1e-6:
                self.te = 0.0
            if e0 > 0.0 or self.te > 0.0:
                ev = e0 + (self.te - e0) * frac
                tv = self.trem_depth * ev * np.sin(
                    2.0 * math.pi * (self.tph + self.trem_hz * self.blk_s * frac))
            else:
                tv = 0.0
            self.tph = (self.tph + self.trem_hz * self.blk_s) % 1.0
            out[b] = 1.0 + wv - sv + tv
        return out


def pitch_level(p, a, b):
    """A family's response to pressure points p (n, SUB + 1): the frequency
    ratio each block -- its mean over the block, which is what the kernel's
    bend row holds -- and the level at the block edges (n + 1 of them)."""
    r = np.mean(p[:, :-1] ** a, axis=1)
    lv = np.concatenate((p[:, 0], p[-1:, -1])) ** b
    return r, lv
