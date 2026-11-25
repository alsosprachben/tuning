"""The organ's wind: one pressure per division, shared by every pipe on its chest.

A pipe organ's pipes stand on a windchest fed by a bellows, and they all
hear its pressure. Three things move it:

  w(t)  THE WANDER. The blower and the regulator never hold perfectly still.
        Filtered noise, slow (under a hertz): a regulator's ripple, 0.3% RMS
        -- 0.2 cents on a flue -- a named size, for the ear. The partials'
        own uncorrelated wobble is the jet's turbulence, which the skirts make
        (phase 2); pressure moves every partial together. (Abel, Ahnert and
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

        ...AND THE REGULATOR BRINGS IT BACK. A reservoir's weights and springs
        restore the static pressure after the swing (wind_regulator_s, the time
        it takes, wind_regulator_restore how fully): what is left of a held
        chord is a breath at its entry and its release, not a lasting dip --
        a released chord's surge the mirror of its entry's sag. And a chest
        has a limit: the swing saturates at wind_sag_max of the static, so a
        full organ is not a negative pressure. The shared wind's FLEXIBILITY
        (wind_flex, by ear: a steady modern regulator to a breathing
        historical one) scales the swing; the forms are the physics' (the
        Rodgers wind patent: slightly to moderately underdamped, a cycle or
        two of ringing; Carlsson 2002: the trunks dominate; Pykett).

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

    def __init__(self, props, blk_s, seed=0, scale=1.0, wander_scale=None):
        self.blk_s = float(blk_s)
        self.scale = float(scale)
        # the wander is the regulator's own, not a matter of flexibility: on
        # at its own level whenever the shared wind is
        ws = self.scale if wander_scale is None else float(wander_scale)
        self.wander_rms = float(getattr(props, 'wind_wander_rms', 0.0)) * ws
        self.reg_s = float(getattr(props, 'wind_regulator_s', 0.0) or 0.0)
        self.reg_restore = float(getattr(props, 'wind_regulator_restore', 1.0))
        self.sag_max = float(getattr(props, 'wind_sag_max', 0.0) or 0.0)
        self.ra = math.exp(-self.blk_s / self.reg_s) if self.reg_s > 0.0 else None
        self.r1 = 0.0
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

    def _dev(self):
        """The pressure's fall below static: the swing less the regulator's
        restoring, saturating at sag_max."""
        d = self.s1 - (self.reg_restore * self.r1 if self.ra is not None else 0.0)
        return _sat(d, self.sag_max)

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
            # the sag, likewise: the reservoir's swing (s), less what the
            # regulator has restored (r, following it), saturating
            s0 = self._dev()
            if self.sag_per_unit > 0.0:
                s = self.c1 * self.s1 + self.c2 * self.s2 + self.g * self.d1
                self.s2, self.s1 = self.s1, s
                self.d1 = float(demand[b]) * self.sag_per_unit
                if self.ra is not None:
                    self.r1 = self.ra * self.r1 + (1.0 - self.ra) * self.s1
            s1 = self._dev()
            sv = s0 + (s1 - s0) * frac
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
                # (libm's sin, point by point: the native engine's too)
                tv = self.trem_depth * ev * np.array(
                    [math.sin(x) for x in 2.0 * math.pi * (self.tph + self.trem_hz * self.blk_s * frac)])
            else:
                tv = 0.0
            self.tph = (self.tph + self.trem_hz * self.blk_s) % 1.0
            out[b] = 1.0 + wv - sv + tv
        return out


def _sat(x, m):
    return m * math.tanh(x / m) if m > 0.0 else x


def pitch_level(p, a, b):
    """A family's response to pressure points p (n, SUB + 1): the frequency
    ratio each block -- its mean over the block, which is what the kernel's
    bend row holds -- and the level at the block edges (n + 1 of them).
    libm's pow (native.xpow) and the mean summed point by point in order:
    the native engine's arithmetic (native/organrows.cpp)."""
    import native as _NV
    q = _NV.xpow(np.ascontiguousarray(p[:, :-1]), a)
    s = q[:, 0].copy()
    for j in range(1, q.shape[1]):
        s = s + q[:, j]
    r = s / float(q.shape[1])
    lv = _NV.xpow(np.concatenate((p[:, 0], p[-1:, -1])), b)
    return r, lv


# ---------------------------------------------------------------- the harmonium
#
# THE HARMONIUM'S WIND (Mustel, L'Orgue-Expressif I, pp. 73-95; tonelib's
# ReedOrganFreeProperties.harmonium_wind_*): not a regulated chest but the
# player's feet. Two wedge pumps push into a small, stiff wind-chest (the
# "caisse a vent": "ce n'est pas un reservoir", p. 148), joined through a
# valve to a RESERVOIR whose springs make its pressure grow with its fill
# ("s'il est plein, les ressorts ... fournissent le Fortissimo", p. 78).
#   THE RESERVOIR (Expression pushed in): pressure = full * fill. The player
#     pumps toward the pressure they mean (CC11, the aim), as fast as the
#     pumps allow (pump_max), reacting over player_s; the reeds' draw drains
#     it. So a crescendo takes "plusieurs coups de pedales", a diminuendo
#     waits on the notes to empty it, and a full chord sags when it draws
#     more than the feet can give.
#   THE FEET (Expression drawn: the reservoir shut off, p. 115): the chest's
#     pressure IS the feet's (the aim), over foot_s -- and still no more than
#     the pumps can feed: a draw past pump_max pulls it down.
#   THE KNEES (Double-Expression, pp. 87-95): each half's compartment is fed
#     through a valve that shuts above its knee's set-point -- the half's
#     pressure is min(chest, set-point), whatever the feet do.
# A reed draws q7 (m3/s at the reference pressure) * (p / ref) ** draw_exp
# (examples/harmonium_bake.py --wind: the simulated reeds' flow). Scalar
# libm arithmetic throughout, block by block, state carried: the native
# engines' (native/channel.cpp, native/slab.cpp) is the same.

class HarmoniumWind:
    """A harmonium channel's chest and its two halves' pressures (Pa),
    block by block. props: the voice's class (its harmonium_wind_*)."""

    SUB = 8

    def __init__(self, props, blk_s):
        import tonelib as T
        self.blk_s = float(blk_s)
        self.ref = float(T.HARMONIUM_PRESSURE_REF)
        self.full = float(props.harmonium_reservoir_full_pa)
        self.vres = float(props.harmonium_reservoir_m3)
        self.qmax = float(props.harmonium_pump_max_m3s)
        self.dexp = float(props.harmonium_draw_exp)
        self.a_player = math.exp(-self.blk_s / float(props.harmonium_player_s))
        self.a_foot = math.exp(-self.blk_s / float(props.harmonium_foot_s))
        self.tau_player = float(props.harmonium_player_s)
        self.fill = 1.0
        self.pc = self.full
        self.sounded = False                # (the player readies the reservoir before the first note)
        self.edge = None                    # the halves' pressures at the last block's end

    def _draw(self, pc, q7, knee):
        d = 0.0
        for h in range(2):
            if q7[h] > 0.0:
                d += q7[h] * math.pow(min(pc, knee[h]) / self.ref, self.dexp)
        return d

    def step(self, q7, aim, expr, knee):
        """One block on: q7 (bass, treble) the sounding reeds' draw at the
        reference, aim the pressure the feet mean, expr the Expression drawn,
        knee (bass, treble) the set-points (inf: hooked off). Returns the
        halves' pressures at the block's end."""
        if not self.sounded:
            # (nothing has sounded yet: the reservoir where the player means
            # to begin, the chest with it)
            self.fill = min(1.0, max(0.0, min(aim, self.full) / self.full))
            self.pc = aim if expr else self.full * self.fill
            if q7[0] == 0.0 and q7[1] == 0.0:
                out = (min(self.pc, knee[0]), min(self.pc, knee[1]))
                if self.edge is None:
                    self.edge = out
                return out
            self.sounded = True
            if self.edge is None:
                self.edge = (min(self.pc, knee[0]), min(self.pc, knee[1]))
        if expr:
            pc = aim + (self.pc - aim) * self.a_foot
            d = self._draw(pc, q7, knee)
            if d > self.qmax:               # (the pumps cannot keep up: the feet sink)
                pc = pc * math.pow(self.qmax / d, 1.0 / self.dexp)
            self.pc = pc
        else:
            p = self.full * self.fill
            d = self._draw(p, q7, knee)
            c = self.vres / self.full
            qp = d + (min(aim, self.full) - p) * c / self.tau_player
            qp = 0.0 if qp < 0.0 else (self.qmax if qp > self.qmax else qp)
            f = self.fill + (qp - d) * self.blk_s / self.vres
            self.fill = 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)
            self.pc = self.full * self.fill
        out = (min(self.pc, knee[0]), min(self.pc, knee[1]))
        if self.edge is None:
            self.edge = out
        return out

    def blocks(self, q7, aim, expr, knee):
        """n blocks: q7 (n, 2), aim (n,), expr (n,), knee (n, 2). Returns
        (points (n, 2, SUB + 1) Pa, each block's ramp from its start edge to
        its end edge; edges (n + 1, 2))."""
        n = len(aim)
        edges = np.empty((n + 1, 2))
        pts = np.empty((n, 2, self.SUB + 1))
        for b in range(n):
            e1 = self.step((float(q7[b][0]), float(q7[b][1])), float(aim[b]), bool(expr[b] >= 0.5),
                           (float(knee[b][0]), float(knee[b][1])))
            e0 = self.edge
            edges[b] = e0
            for h in range(2):
                for j in range(self.SUB + 1):
                    pts[b, h, j] = e0[h] + (e1[h] - e0[h]) * (j / float(self.SUB))
            self.edge = e1
        edges[n] = self.edge
        return pts, edges


def harmonium_rows(cls, pts, edges, opening=None):
    """A stop's rows from its half's pressure: the pitch ratio each block (its
    mean over the block's points, summed in order: the kernel's bend row) and
    the level at the block edges -- tonelib.harmonium_pitch_ratio and
    harmonium_level_gain, point by point -- a back stop's times its box's
    (tonelib.harmonium_box_level, the lids' opening at each edge)."""
    import tonelib as T
    n = pts.shape[0]
    r = np.empty(n)
    for b in range(n):
        s = 0.0
        for j in range(pts.shape[1] - 1):
            s = s + T.harmonium_pressure_ratio(cls, float(pts[b, j]))
        r[b] = s / float(pts.shape[1] - 1)
    lv = np.array([T.harmonium_level_gain(cls, float(x)) for x in edges])
    if opening is not None and getattr(cls, 'box_back', False):
        lv = np.array([lv[i] * T.harmonium_box_level(float(opening[i])) for i in range(len(lv))])
    return r, lv
