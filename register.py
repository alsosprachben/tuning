#!/usr/bin/env python3
"""The strings nobody struck: a piano's free-string register.

When the damper pedal is down every string is free, and each strike drives
them through the bridge. Lehtonen, Penttinen, Rauhala and Valimaki (JASA 122,
2007) measured what that does: partial decay times change, mostly in the
middle register; the beating between unison strings changes; and the
residual's energy grows. Zambon, Lehtonen and Bank (DAFx-08) modelled the free
strings as a bank of resonators driven by the bridge force -- linear, and
feed-forward (the register does not act back on the string that drives it).
This is that model, solved exactly rather than filtered.

THE REGISTER IS THE RENDERED STRINGS. A key's modes are the partials the note
loop emits for that key -- blockrender.string_partial / partial_decay /
unison_partial, shared and not copied -- at the tuning table in force, with
the key's own inharmonicity, unison detune and pitch error (a fact of the
key, see GrandPianoProperties). A struck partial and the same string ringing
sympathetically cannot disagree, so what the register does with a temperament
is what that temperament's strings would do: coincident partials resonate,
mistuned ones beat and die away, by exactly their offset.

THE RESPONSE IS SOLVED, NOT ASSUMED. A free mode m (frequency W_m, decay a_m)
driven by a partial i (W_i, decay b_i) obeys, for the complex envelope,

    z' = (iW_m - a_m) z + c e^{(iW_i - b_i)t}

whose solution from rest is

    z(t) = c [e^{(iW_i-b_i)t} - e^{(iW_m-a_m)t}] / [(iW_i-b_i) - (iW_m-a_m)].

Two parts. The FREE part rings at the mode's own frequency and decay: the halo,
the string that was not struck. The FORCED part follows the driver: it is the
register's colouring of the struck note -- Lehtonen's changed decay and
beating, falling out of the equation rather than imposed. The steady-state
Lorentzian (tonelib.sympathetic_partials) is this formula's long-time limit.

A hard strike's partials start sharp and settle (tension_bend: the kernel's
tbav * e^{-t/tau}, cut at tcut). For a driver that glides, the free part is
the integral y(T) = int c e^{i(Phi_i(t) - W_m t) + (a_m - b_i) t} dt in the
mode's rotating frame -- Phi_i the kernel's own glide phase -- integrated
numerically over the glide and in closed form after it.

When a driver's damper falls the forcing stops, and what the forced part held
is handed to the free part at that instant: energy is continuous through the
damper.

THE KNOCK. The hammer's impulse through the bridge kicks every free string at
its own modes whatever the interval: a free part only, falling with distance
along the bridge.

AS ROWS. A mode is one sinusoid, so excitations add as phasors on the
absolute clock (the kernel's carrier is analytic). A mode's free part is a
chain of segments: when an excitation changes it, the open segment ends and a
new one starts on the same 512-sample block edge (noff = non, fa = re = BLK),
which the kernel's per-block envelope turns into an exact crossfade. A
segment ends at its string's damper (pedal up, or its key let go) or where it
falls under the floor. The forced parts of all the modes one driver partial
reaches share its frequency and decay, so they are ONE row per driver partial
per decay stage, riding the driver's envelope and damper. Direct sound only:
the register reaches the room through the send and the late tail.
"""
import math
import random

import numpy as np

import tonelib as T

TAU = 2.0 * math.pi
KEYS = range(21, 109)            # A0..C8, the piano's 88
FLOOR = 1e-3                     # -60 dB of the strike's loudest partial
SPLIT = 1e-2                     # a change under -40 dB of a mode waits for the next


class Strings(object):
    """Every string of every key of one piano class at one tuning, as arrays:
    a mode is (key, string, harmonic) at its emitted frequency and decay."""

    def __init__(self, pc, table, pan, chan_vol, sr, bridge):
        # UNA CORDA SHIFTS THE HAMMER; the free strings are all still there.
        # unison_voices reads the soft pedal's module flag when it is CALLED,
        # so it is held up for the whole build -- not just while each key's
        # properties are made, which left the register's strings depending on
        # whether the soft pedal happened to be down when it was built.
        soft = T.soft_pedal_down
        T.soft_pedal_down = False
        try:
            self._build(pc, table, pan, chan_vol, sr, bridge)
        finally:
            T.soft_pedal_down = soft

    def _build(self, pc, table, pan, chan_vol, sr, bridge):
        sp, sa, sm = bridge
        k_, s_, m_, f_, a_, w_, hl_, hr_, dl_, dr_, px_ = ([] for _ in range(11))
        self.props = {}
        for key in KEYS:
            if key not in table:
                continue
            f0 = float(table[key])
            p = _isolated(pc, f0, pan, chan_vol)
            self.props[key] = p
            B = p.inharmonicity_coefficient
            pj = 1.0 + getattr(p, 'pitch_jitter', 0.0)
            li, ri = p.left_incidence, p.right_incidence
            dl = getattr(p, 'left_hrtf_delay', 0.0) * sr
            dr = getattr(p, 'right_hrtf_delay', 0.0) * sr
            px = getattr(p, 'position_x', 0.0)
            for m in range(1, p.max_harmonic + 1):
                hh = sp(p, f0, 1.0, m, B)
                if hh is None:
                    break
                h, hf = hh
                if hf > sr / 2:
                    break
                if p.harmonic_volume(m) == 0.0:
                    continue            # the note loop emits no such partial
                dbps, logr, aftL, logrA = sa(p, f0, m)
                strings = [(0, hf, logrA if logrA > 0 else logr)]
                for ui, (gm, off_hz, drr, ud, uph) in enumerate(p.unison_voices(f0, m, dbps)):
                    uf, ulr = sm(hf, off_hz, drr, ud)
                    if uf <= 0 or uf > sr / 2:
                        continue
                    _, uadb = p.aftersound(f0, ud)
                    ua = math.log(T.db_ratio(uadb)) if uadb > 0 else ulr
                    strings.append((ui + 1, uf, ua))
                # the bridge's admittance at the mode, which couples it both ways
                w = p.soundboard_gain(hf) * p.radiation_gain(hf)
                for si, fz, al in strings:
                    k_.append(key); s_.append(si); m_.append(m)
                    f_.append(fz * pj); a_.append(al); w_.append(w)
                    hl_.append(p.hrtf_gain(hf, li)); hr_.append(p.hrtf_gain(hf, ri))
                    dl_.append(dl); dr_.append(dr); px_.append(px)
        o = np.argsort(np.asarray(f_), kind='stable')
        A = lambda v, t=np.float64: np.asarray(v, t)[o]          # noqa: E731
        self.key, self.string, self.harm = A(k_, np.int64), A(s_, np.int64), A(m_, np.int64)
        self.f, self.alpha, self.w = A(f_), A(a_), A(w_)
        self.w = self.w / max(float(self.w.max()), 1e-30)
        self.hl, self.hr, self.dl, self.dr, self.px = A(hl_), A(hr_), A(dl_), A(dr_), A(px_)
        self.W = TAU * self.f


def _isolated(pc, f0, pan, chan_vol):
    """A key's properties, built without moving anything else: the global
    random stream every later note draws from, and the soft pedal (una corda
    shifts the HAMMER; the free strings are all still there)."""
    st, soft = random.getstate(), T.soft_pedal_down
    T.soft_pedal_down = False
    try:
        p = pc(f0, pan, 1.0, chan_vol)
    finally:
        random.setstate(st)
        T.soft_pedal_down = soft
    if p.inharmonicity_dynamic:
        p.inharmonicity_coefficient = p.inharmonicity_coefficient_for_frequency(f0)
    return p


# ------------------------------------------------------------------ the response

def stages(aft, sus, logr, logrA):
    """A driver partial's envelope as exponentials: [(weight, rate /s)] --
    the kernel's dc = sl + (1-sl)((1-af) e^{-lr t} + af e^{-lrA t})."""
    out = []
    if (1.0 - sus) * (1.0 - aft) > 0:
        out.append(((1.0 - sus) * (1.0 - aft), logr))
    if (1.0 - sus) * aft > 0:
        out.append(((1.0 - sus) * aft, logrA))
    if sus > 0:
        out.append((sus, 0.0))
    return out


def glide_phase(Wi, tb, tau, cut, t):
    """The kernel's tension glide, as phase added to W_i t: W_i tb tau (1 - e^{-min(t,cut)/tau})."""
    return Wi * tb * tau * (1.0 - np.exp(-np.minimum(t, cut) / tau))


NEAR = 30.0                      # pairs within this many glide-widths are integrated
STEP = 0.02                      # s: the glide's curvature is ~80 rad/s^2 at most


def _glide_grid(cut, tau):
    """Times from 0 to cut, each step STEP/2 * e^{t / 2 tau}: the linear
    exponent's error goes with the glide's curvature, which falls as
    e^{-t/tau}, so the step may grow as its square root does."""
    t = [0.0]
    while t[-1] < cut:
        t.append(min(cut, t[-1] + 0.5 * STEP * math.exp(t[-1] / (2.0 * tau))))
    return np.array(t)


def free_part(c, Wi, bi, Wm, am, tb=0.0, tau=1.0, cut=0.0, need=0.0):
    """The free part's complex amplitude, referenced to the driver's onset (its
    phase there 0): what multiplies e^{(iW_m - a_m) t}. Also the forced
    coefficient, what multiplies the driver (whose own phase carries the
    glide). Vectorised over pairs.

    NEAR pairs -- within NEAR glide-widths of coincidence -- are integrated over
    the glide, y' = c e^{g(t)}, g = i(Phi_i(t) - W_m t) + (a_m - b_i) t, each
    STEP exactly with g taken linear across it (the curvature is the glide's
    alone, so the step does not depend on the offset). FAR pairs follow the
    glide adiabatically: their free part is set at the strike, where the driver
    is at W_i (1 + tb), and the forced part follows. Without a glide both are
    the closed form."""
    scalar = np.ndim(Wi) == np.ndim(Wm) == np.ndim(c) == 0
    Wi, bi, Wm, am, c, tb, tau, cut = np.broadcast_arrays(
        *[np.atleast_1d(np.asarray(v, float) if k != 4 else np.asarray(v)) for k, v in
          enumerate((Wi, bi, Wm, am, c, tb, tau, cut))])
    D = (1j * Wi - bi) - (1j * Wm - am)
    forced = c / D
    if not np.any(tb):
        return (-forced[0], forced[0]) if scalar else (-forced, forced)
    D0 = (1j * Wi * (1.0 + tb) - bi) - (1j * Wm - am)
    free = -c / D0
    width = np.abs(Wi * tb) + np.abs(am - bi) + 1.0
    # integrated where the glide matters AND the answer can reach `need` (a
    # pair whose whole response is under it has an adiabatic error under it too)
    near = (tb != 0) & (np.abs(Wi - Wm) < NEAR * width) & (np.abs(free) >= need)
    if np.any(near):
        wi, wm, b_, a_, cc = Wi[near], Wm[near], bi[near], am[near], c[near]
        tb_, ta_, cu_ = tb[near], tau[near], cut[near]
        # one grid for all (the glide's settle time and cut are the strike's)
        grid = _glide_grid(float(cu_.max()), float(ta_.max()))

        def integral(tt):
            tt = tt[:, None] * np.ones_like(cu_)[None, :]
            tt = np.minimum(tt, cu_[None, :])
            g = 1j * ((wi - wm) * tt + glide_phase(wi, tb_, ta_, cu_, tt)) + (a_ - b_) * tt
            dt = tt[1:] - tt[:-1]
            sl = (g[1:] - g[:-1]) / np.where(dt > 0, dt, 1.0)
            with np.errstate(divide='ignore', invalid='ignore'):
                seg = np.where(np.abs(sl * dt) > 1e-9, np.exp(g[:-1]) * np.expm1(sl * dt) / sl,
                               np.exp(g[:-1]) * dt)
            return seg.sum(0)
        # each step exact for a linear exponent leaves an error of order dt^2 from
        # the glide's curvature; Richardson's combination of the grid and its
        # halving cancels it
        half = np.sort(np.concatenate([grid, 0.5 * (grid[1:] + grid[:-1])]))
        y = cc * (4.0 * integral(half) - integral(grid)) / 3.0
        # after the cut: constant frequency, its phase carrying the glide
        th = glide_phase(wi, tb_, ta_, cu_, cu_)
        free[near] = y - forced[near] * np.exp(1j * th + (1j * (wi - wm) + (a_ - b_)) * cu_)
    return (free[0], forced[0]) if scalar else (free, forced)


def knock_phase(seed, n):
    return np.random.RandomState(seed & 0x7fffffff).uniform(0.0, TAU, n)


# ------------------------------------------------------------------ the pass

def _merge(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


class Channel(object):
    """One piano channel's free strings through a piece, INCREMENTALLY: fed
    each strike as its note is emitted, it works through the events no note to
    come can change and hands out rows once nothing to come can change them.
    The whole table feeds it every strike and then finishes it; the stream
    feeds and advances it note by note. One code path, so the two agree.

    What is final when. A strike block is complete once the next onset T is
    past its end; a driver's damper hand-over is processed once every block
    before it is. A free string's span is known exactly up to T (a span is
    the pedal's, the key's own holds, or forever above the dampers -- and a
    hold that could extend it starts before its end), so a free row's end is
    settled once it is no later than the first event still to come. A bridge
    waits until its start is past T. Forced rows are final when made.

    Rows are ordered (phase, seq): the timeline's free and bridge rows in the
    order they were made, then the forced rows."""

    def __init__(self, ch, strings, props, pedal, sr, blk, cols, scale=1.0, keep=True):
        self.ch, self.S, self.sr, self.blk, self.cols = ch, strings, sr, blk, cols
        self.keep = keep             # keep each strike's driver rows once used (the
                                     # whole table, which holds every row anyway)
        P = props
        self.kappa = float(getattr(P, 'register_gain', 0.0)) * scale
        self.knock = float(getattr(P, 'register_knock_gain', 0.0)) * scale
        self.fall = float(getattr(P, 'register_knock_falloff', 0.0))
        self.top = int(getattr(P, 'damper_top', 128))
        self.rel = float(getattr(P, 'release_valve_time', 0.12) or 0.12) * sr
        self.pedal = [(a * sr, b * sr) for a, b in pedal]
        self.holds = {}              # key -> [(n0, n1)] known so far
        self.spans = {}              # key -> merged spans (a cache)
        self.endmemo = {}            # key -> {sample: span end} (a cache)
        self.keyidx = {k: np.flatnonzero(strings.key == k) for k in strings.props}
        M = len(strings.f)
        self.Az = np.zeros(M, complex); self.nref = np.zeros(M)
        self.Rz = np.zeros(M, complex); self.rref = np.zeros(M)
        self.rrec = [None] * M        # each mode's latest free row (its record)
        # ...and what its end turns on, as arrays: the row's start, where it
        # falls under the floor, where a split closed it
        self.has = np.zeros(M, bool)
        self.r_b = np.zeros(M); self.r_nfloor = np.zeros(M); self.r_closed = np.full(M, np.inf)
        self.strikes = []
        self.groups = {}             # block -> [strike index]
        self.pending = {}            # damper block -> transfer amplitudes
        self.bridges = []            # undecided: (seqs, modes, values, n0, re0, pb, src)
        self.open = []               # free rows not yet final
        self.out = []                # final rows not yet handed out
        self.seq = 0
        self.fseq = 0
        self.loud = 0.0              # the loudest partial so far: the floor's reference
        self.template = None
        self.T = 0.0

    # -- the free spans, as known ----------------------------------------------
    def _span_list(self, key):
        sp = self.spans.get(key)
        if sp is None:
            if key >= self.top:
                sp = [(0.0, float('inf'))]
            else:
                sp = _merge(self.pedal + self.holds.get(key, []))
            self.spans[key] = sp
        return sp

    def span_end(self, key, n):
        """The end of the free span holding sample n, or None."""
        memo = self.endmemo.get(key)
        if memo is None:
            memo = self.endmemo[key] = {}
        got = memo.get(n, memo)
        if got is not memo:
            return got
        out = None
        for a, b in self._span_list(key):
            if a <= n < b:
                out = b
                break
            if a > n:
                break
        memo[n] = out
        return out

    @property
    def floor(self):
        return FLOOR * max(self.loud, 1e-30)

    # -- strikes in -----------------------------------------------------------
    def strike(self, key, on, held, av, rows):
        """A strike: its key, onset and the time its key came up (s), and its
        rows as {column: array} -- every column, the whole note."""
        sr, blk = self.sr, self.blk
        d = np.flatnonzero(np.asarray(rows['dr']) > 0.5)
        self.holds.setdefault(key, []).append((on * sr, held * sr))
        self.spans.pop(key, None)
        self.endmemo.pop(key, None)
        if not len(d):
            return
        si = len(self.strikes)
        drv = {c: np.asarray(rows[c])[d] for c in self.cols}
        self.strikes.append(dict(key=key, av=av, drv=drv))
        b = int(float(drv['non'].min()) // blk) * blk
        self.groups.setdefault(b, []).append(si)
        if self.template is None:
            self.template = {c: drv[c][0] for c in self.cols}

    # -- the timeline ---------------------------------------------------------
    def advance(self, T):
        """Work through every event no onset at or after T can change."""
        self.T = T
        blk = self.blk
        while True:
            gb = min((b for b in self.groups if b + blk <= T), default=None)
            pb = min((p for p in self.pending if p <= T), default=None)
            if gb is None and pb is None:
                break
            if pb is not None and (gb is None or pb <= gb):
                add = self.pending.pop(pb)
                self._update(add != 0, pb, add, ('damper', pb))
            else:
                sis = self.groups.pop(gb)
                self._strikes(gb, sis)
                if not self.keep:
                    for si in sis:
                        self.strikes[si]['drv'] = None
        self._decide_bridges(T)
        self._settle_rows()

    def finish(self):
        self.advance(float('inf'))

    def next_event(self):
        """The earliest time an event still to come can act at."""
        e = float('inf')
        if self.groups:
            e = min(e, min(self.groups))
        if self.pending:
            e = min(e, min(self.pending))
        if self.T != float('inf'):
            e = min(e, float(int(self.T // self.blk) * self.blk))
        return e

    def pending_min(self):
        """The earliest onset a row not yet handed out may have."""
        m = self.next_event()
        for r in self.open:
            m = min(m, r['row']['non'])
        for br in self.bridges:
            m = min(m, br[3])
        return m

    def _strikes(self, b, sis):
        S, sr, blk = self.S, self.sr, self.blk
        Wm, am = S.W, S.alpha
        M = len(S.f)
        add = np.zeros(M, complex)
        for si in sis:
            st = self.strikes[si]
            drv = st['drv']
            self.loud = max(self.loud, float(np.max(np.abs(drv['aM']))))
            floor = self.floor
            free = np.zeros(M, bool)
            for k, ix in self.keyidx.items():
                if k != st['key'] and self.span_end(k, b) is not None:
                    free[ix] = True
            if not free.any():
                continue
            fi = np.flatnonzero(free)
            fW = Wm[fi]
            xfer = np.zeros(M, complex)
            n_off = None
            for r in range(len(drv['om'])):
                a_i = float(drv['aM'][r])
                if a_i < floor:
                    continue
                om_i = float(drv['om'][r]); Wi = om_i * sr
                n_i = float(drv['non'][r])
                theta = om_i * n_i + float(drv['p0'][r]) + om_i * float(drv['delL'][r])
                n_off, re_off = float(drv['noff'][r]), float(drv['re'][r])
                tb, ta, cu = float(drv['tbav'][r]), float(drv['tau'][r]), float(drv['tcut'][r])
                for wgt, beta in stages(float(drv['aft'][r]), float(drv['sus'][r]),
                                        float(drv['logr'][r]), float(drv['logrA'][r])):
                    cmax = self.kappa * a_i * wgt
                    if cmax <= 0:
                        continue
                    reach = cmax / (floor * SPLIT)          # |D| past which it is lost
                    lo = np.searchsorted(fW, Wi - reach); hi = np.searchsorted(fW, Wi + reach)
                    if hi <= lo:
                        continue
                    j = fi[lo:hi]
                    fr, fo = free_part(cmax * S.w[j], Wi, beta, Wm[j], am[j], tb, ta, cu,
                                       need=floor * SPLIT)
                    # free: from the driver's onset, at the mode's own frequency
                    add[j] += fr * np.exp(1j * (theta - Wm[j] * n_i / sr) + am[j] * (n_i - b) / sr)
                    # forced: one row riding this driver's stage, relative to it
                    F = complex(fo.sum())
                    if abs(F) > floor * SPLIT:
                        self._forced(drv, r, beta, F / a_i, si)
                    # what the forced part holds when this driver's damper falls
                    tq = (n_off - n_i) / sr
                    gq = glide_phase(Wi, tb, ta, cu, tq)
                    xfer[j] += fo * np.exp(1j * (theta + Wi * tq + gq - Wm[j] * n_off / sr)
                                           - beta * tq)
            if self.knock > 0:
                dk = np.abs(S.key[fi] - st['key'])
                amp = self.knock * float(np.max(drv['aM'])) * S.w[fi] \
                    * 10.0 ** (-self.fall * dk / 20.0)
                add[fi] += amp * np.exp(1j * knock_phase(hash((self.ch, si)), len(fi)))
            if n_off is not None and np.any(xfer):
                pb = int(math.ceil((n_off + re_off) / blk)) * blk
                cand = np.flatnonzero(np.abs(xfer) >= floor)
                if len(cand):
                    seqs = list(range(self.seq, self.seq + len(cand)))
                    self.seq += len(cand)
                    self.bridges.append((seqs, cand, xfer[cand], n_off, re_off, pb, ('damper', si)))
                tr = xfer * np.exp(-am * (pb - n_off) / sr)
                self.pending[pb] = self.pending[pb] + tr if pb in self.pending else tr
        self._update(np.abs(add) > 0, b, add, ('strike', b))

    def ends(self, keys, times):
        """span_end over arrays, NaN for "not free": once per distinct
        (key, time) pair -- a key's strings share their spans, and an update
        asks about few distinct times."""
        out = np.empty(len(keys))
        if not len(keys):
            return out
        tu, ti = np.unique(times, return_inverse=True)
        code = np.ravel(ti).astype(np.int64) * 256 + keys.astype(np.int64)
        cu, inv = np.unique(code, return_inverse=True)
        vals = np.array([np.nan if e is None else e for e in
                         (self.span_end(int(c % 256), float(tu[c // 256])) for c in cu)])
        return vals[np.ravel(inv)]

    def _update(self, m, b, add, src):
        """Mode set m gains `add` (referenced to block b), then settles. A
        string whose damper fell since its last update starts from rest."""
        S, am, sr = self.S, self.S.alpha, self.sr
        Az, nref = self.Az, self.nref
        idx = np.flatnonzero(m)
        if not len(idx):
            return
        live = idx[Az[idx] != 0]
        if len(live):
            e = self.ends(S.key[live], nref[live])
            e = np.where(np.isnan(e), nref[live], e)
            dead = live[e <= b]
            Az[dead] = 0; nref[dead] = b
        Az[idx] = Az[idx] * np.exp(-am[idx] * np.maximum(b - nref[idx], 0.0) / sr) + add[idx]
        nref[idx] = b
        # split the modes whose row has drifted from the truth
        floor = self.floor
        tz = Az[idx]
        has = self.has[idx]
        rz = np.zeros(len(idx), complex)
        if has.any():
            h = idx[has]
            end = self.ends(S.key[h], self.r_b[h])
            end = np.where(np.isnan(end), self.r_b[h], end)
            alive = np.minimum(np.minimum(self.r_nfloor[h], end), self.r_closed[h]) > b
            rz[has] = np.where(alive, self.Rz[h] * np.exp(-am[h] * np.maximum(b - self.rref[h], 0.0) / sr), 0)
        mag = np.maximum(np.abs(tz), floor)
        go = idx[np.abs(tz - rz) > SPLIT * mag]
        if not len(go):
            return
        free_now = ~np.isnan(self.ends(S.key[go], np.full(len(go), float(b))))
        for i, fr in zip(go, free_now):
            rec = self.rrec[i]
            if rec is not None:
                if rec['closed'] is None or rec['closed'] > b:
                    rec['closed'] = float(b)
                    self.r_closed[i] = float(b)
            self.rrec[i] = None
            self.has[i] = False
            z = Az[i]
            if abs(z) < floor or not fr:
                continue
            n_floor = b + sr * math.log(abs(z) / floor) / max(am[i], 1e-9)
            rec = self._write(i, z, b, self.blk, None, None, 'free', src)
            rec.update(mode=i, b=float(b), key=int(S.key[i]), n_floor=n_floor, closed=None)
            self.open.append(rec)
            self.rrec[i] = rec
            self.has[i] = True
            self.r_b[i] = b; self.r_nfloor[i] = n_floor; self.r_closed[i] = np.inf
            self.Rz[i] = z; self.rref[i] = b

    def _alive(self, rec, b):
        """Whether a free row still sounds at b, as far as it can be known."""
        end = self.span_end(rec['key'], rec['b'])
        x = min(rec['n_floor'], end if end is not None else rec['b'])
        if rec['closed'] is not None:
            x = min(x, rec['closed'])
        return x > b

    def _write(self, i, z, non, fa, noff, re_, kind, src, seq=None):
        S, sr = self.S, self.sr
        om = S.W[i] / sr
        ph = math.atan2(z.imag, z.real)
        row = dict(self.template)
        row.update(om=om, p0=ph - om * S.dl[i], p0R=ph - om * S.dr[i],
                   aL=abs(z) * S.hl[i], aR=abs(z) * S.hr[i], aM=abs(z),
                   nf=S.f[i], nfr=S.f[i], non=float(non), noff=noff,
                   fa=float(fa), re=re_, logr=float(S.alpha[i]), logrA=0.0, aft=0.0,
                   sus=0.0, cv=0.0, sj=0.0, crl=0.0, csc=0.0, cbw=0.0, tbav=0.0,
                   tcut=0.0, gb=0.0, gc=0.0, vd=0.0, vdl=0.0, br=-1, gr=-1, cr=0,
                   delL=S.dl[i], delR=S.dr[i], px=S.px[i], pl=int(S.string[i]),
                   fx=-1, mk=0, rdl=0.0, fmw=0.0, fmp=0.0, fmpR=0.0, dr=1.0)
        if seq is None:
            seq = self.seq; self.seq += 1
        return dict(row=row, phase=0, seq=seq, kind=kind, src=src, mode=int(i))

    def _forced(self, drv, r, beta, F, si):
        row = {c: drv[c][r] for c in self.cols}
        g = abs(F)
        ph = math.atan2(F.imag, F.real)
        row.update(aL=row['aL'] * g, aR=row['aR'] * g, aM=row['aM'] * g,
                   p0=row['p0'] + ph, p0R=row['p0R'] + ph,
                   logr=beta, logrA=0.0, aft=0.0, sus=0.0 if beta else 1.0)
        rec = dict(row=row, phase=1, seq=self.fseq, kind='forced', src=('strike', si), mode=-1)
        self.fseq += 1
        self.out.append(rec)

    def _decide_bridges(self, T):
        """THE HAND-OVER AT A DAMPER, once whether each string is free at its
        start is known. As the driver's release fades its forced rows out over
        re0 (a smoothstep from n0), these fade the same values in at the modes'
        own frequencies -- the free continuation of what the forced part held
        -- so the two sum without a step; at the block pb after the release
        the chain takes them over (_update, from `pending`)."""
        keep = []
        for br in self.bridges:
            seqs, cand, vals, n0, re0, pb, src = br
            if n0 >= T:
                keep.append(br)
                continue
            for sq, i, z in zip(seqs, cand, vals):
                if self.span_end(int(self.S.key[i]), n0) is None:
                    continue
                rec = self._write(i, z, n0, max(re0, 1.0), float(pb), float(self.blk),
                                  'bridge', src, seq=sq)
                self.out.append(rec)
        self.bridges = keep

    def _settle_rows(self):
        """Free rows whose end nothing to come can change: settled, handed out."""
        e = self.next_event()
        keep = []
        for rec in self.open:
            end = self.span_end(rec['key'], rec['b'])
            exact = end is not None and end < self.T
            x = min(rec['n_floor'], rec['closed'] if rec['closed'] is not None else float('inf'),
                    end if exact else float('inf'))
            if x <= e or self.T == float('inf'):
                end = end if end is not None else rec['b']
                noff, re_ = (end, self.rel) if end <= rec['n_floor'] else (rec['n_floor'], float(self.blk))
                if rec['closed'] is not None and noff > rec['closed']:
                    noff, re_ = rec['closed'], float(self.blk)
                rec['row']['noff'] = float(min(noff, 9e15))
                rec['row']['re'] = float(re_)
                self.out.append(rec)
            else:
                keep.append(rec)
        self.open = keep

    def take(self):
        """The rows final since the last take, each with its (phase, seq)."""
        got, self.out = self.out, []
        return got


def channel_for(ch, R, sr, blk, cols, scale, string_fns, keep=True):
    """A Channel from prepare()'s record of a register channel (its class,
    first props, pan, volume, tuning table and pedal spans)."""
    S = R.get('strings') or Strings(R['pc'], R['table'], R['pan'], R['chan_vol'], sr, string_fns)
    return Channel(ch, S, R['props'], R['pedal'], sr, blk, cols, scale, keep)


def expand(A, channels, sr, blk, cols, meta=None):
    """The whole table's way: every register channel fed all its strikes,
    finished, its rows appended in (phase, seq) order -- the order the
    stream's keys put them in. channels: {ch: Channel, with its strikes fed}.
    Returns the number of rows added."""
    added = 0
    for ch, C in channels.items():
        C.finish()
        recs = sorted(C.take(), key=lambda r: (r['phase'], r['seq']))
        for c in cols:
            A[c].extend([r['row'][c] for r in recs])
        if meta is not None:
            meta.extend((ch, r['kind'], r['src'], r['mode']) for r in recs)
        added += len(recs)
    return added


# ------------------------------------------------------------------ live

class LiveChannel(object):
    """The register LIVE (live.py): the same strings and the same response,
    driven by events as they happen. Nothing about the future is known, so
    the caller says which strings are free at each event (the pedal, the keys
    held, the undamped top), and damps strings itself when their dampers fall.
    It runs on a worker thread; what it returns is placed on the audio thread
    a block or two later, at the placing block -- never in the past, which
    would start a row at full level, a click.

    strike()  -> the modes to (re)stamp, each its state Z at sample `at`, and
                 the forced coefficients, one per driver partial and stage
    release() -> the hand-over at that strike's damper: the same, for the
                 modes its forced part held
    damp()    -> forget the modes whose dampers fell (the caller ended them)"""

    def __init__(self, strings, props, sr, scale=1.0):
        P = props
        self.S, self.sr = strings, sr
        self.kappa = float(getattr(P, 'register_gain', 0.0)) * scale
        self.knock = float(getattr(P, 'register_knock_gain', 0.0)) * scale
        self.fall = float(getattr(P, 'register_knock_falloff', 0.0))
        self.top = int(getattr(P, 'damper_top', 128))
        M = len(strings.f)
        self.keyidx = {k: np.flatnonzero(strings.key == k) for k in strings.props}
        self.Az = np.zeros(M, complex); self.nref = np.zeros(M)
        self.Rz = np.zeros(M, complex); self.rref = np.zeros(M)    # what is stamped
        self.stamped = np.zeros(M, bool)
        self.held = {}               # strike id -> its forced parts, for the hand-over
        self.loud = 0.0

    def mask(self, keys):
        m = np.zeros(len(self.S.f), bool)
        for k in keys:
            ix = self.keyidx.get(k)
            if ix is not None:
                m[ix] = True
        return m

    def _settle(self, touched, at):
        """The touched modes whose stamped row has drifted: (modes, Z at `at`)."""
        am, sr = self.S.alpha, self.sr
        idx = np.flatnonzero(touched)
        if not len(idx):
            return idx, np.zeros(0, complex)
        tz = self.Az[idx]
        rz = np.where(self.stamped[idx],
                      self.Rz[idx] * np.exp(-am[idx] * np.maximum(at - self.rref[idx], 0.0) / sr), 0)
        floor = FLOOR * max(self.loud, 1e-30)
        go = np.abs(tz - rz) > SPLIT * np.maximum(np.abs(tz), floor)
        idx, z = idx[go], tz[go]
        self.Rz[idx] = z; self.rref[idx] = at
        self.stamped[idx] = np.abs(z) >= floor
        return idx, z

    def strike(self, sid, key, at, drv, free_keys):
        """A strike at sample `at` of `key`, its stamped direct rows `drv`
        ({om, p0, delL, aM, non, logr, logrA, aft, sus, tbav, tau, tcut, slot}),
        with these keys' strings free."""
        S, sr = self.S, self.sr
        Wm, am = S.W, S.alpha
        M = len(S.f)
        free = self.mask(k for k in free_keys if k != key)
        self.loud = max(self.loud, float(np.max(drv['aM'])) if len(drv['aM']) else 0.0)
        floor = FLOOR * max(self.loud, 1e-30)
        add = np.zeros(M, complex)
        forced, keep = [], []
        fi = np.flatnonzero(free)
        if len(fi) and self.kappa > 0:
            fW = Wm[fi]
            for r in range(len(drv['om'])):
                a_i = float(drv['aM'][r])
                if a_i < floor:
                    continue
                om_i = float(drv['om'][r]); Wi = om_i * sr
                n_i = float(drv['non'][r])
                theta = om_i * n_i + float(drv['p0'][r]) + om_i * float(drv['delL'][r])
                tb, ta, cu = float(drv['tbav'][r]), float(drv['tau'][r]), float(drv['tcut'][r])
                for wgt, beta in stages(float(drv['aft'][r]), float(drv['sus'][r]),
                                        float(drv['logr'][r]), float(drv['logrA'][r])):
                    cmax = self.kappa * a_i * wgt
                    if cmax <= 0:
                        continue
                    reach = cmax / (floor * SPLIT)
                    lo = np.searchsorted(fW, Wi - reach); hi = np.searchsorted(fW, Wi + reach)
                    if hi <= lo:
                        continue
                    j = fi[lo:hi]
                    fr, fo = free_part(cmax * S.w[j], Wi, beta, Wm[j], am[j], tb, ta, cu,
                                       need=floor * SPLIT)
                    add[j] += fr * np.exp(1j * (theta - Wm[j] * n_i / sr) + am[j] * (n_i - at) / sr)
                    F = complex(fo.sum())
                    if abs(F) > floor * SPLIT:
                        forced.append((int(drv['slot'][r]), wgt, beta, F / a_i))
                    keep.append((j, fo, Wi, beta, theta, n_i, tb, ta, cu))
        if self.knock > 0 and len(fi):
            dk = np.abs(S.key[fi] - key)
            amp = self.knock * self.loud_of(drv) * S.w[fi] * 10.0 ** (-self.fall * dk / 20.0)
            add[fi] += amp * np.exp(1j * knock_phase(hash(('live', sid)), len(fi)))
        self.held[sid] = keep
        touched = np.abs(add) > 0
        self.Az[touched] = self.Az[touched] * np.exp(
            -am[touched] * np.maximum(at - self.nref[touched], 0.0) / sr) + add[touched]
        self.nref[touched] = at
        idx, z = self._settle(touched, at)
        return idx, z, forced

    @staticmethod
    def loud_of(drv):
        return float(np.max(drv['aM'])) if len(drv['aM']) else 0.0

    def release(self, sid, at, free_keys):
        """The strike's damper fell at sample `at`: what its forced part held
        goes on at the free modes' own frequencies."""
        keep = self.held.pop(sid, None)
        if not keep:
            return np.zeros(0, np.int64), np.zeros(0, complex)
        S, sr = self.S, self.sr
        Wm, am = S.W, S.alpha
        free = self.mask(free_keys)
        add = np.zeros(len(S.f), complex)
        for j, fo, Wi, beta, theta, n_i, tb, ta, cu in keep:
            tq = (at - n_i) / sr
            gq = glide_phase(Wi, tb, ta, cu, tq)
            add[j] += fo * np.exp(1j * (theta + Wi * tq + gq - Wm[j] * at / sr) - beta * tq)
        add[~free] = 0
        touched = np.abs(add) > 0
        self.Az[touched] = self.Az[touched] * np.exp(
            -am[touched] * np.maximum(at - self.nref[touched], 0.0) / sr) + add[touched]
        self.nref[touched] = at
        return self._settle(touched, at)

    def damp(self, keys):
        """These keys' dampers fell: their strings are at rest."""
        m = self.mask(keys)
        self.Az[m] = 0; self.Rz[m] = 0; self.stamped[m] = False


def live_worker(conn):
    """live.py's register worker, in a PROCESS of its own: the response is
    Python-heavy, and a thread doing it took the interpreter lock from the
    audio callback (a pedal-up block went 1.9 -> 6.7 ms against a 2.67 ms
    budget). Jobs in, results out, over a pipe:

      ('build', pid, pc, tuner, rate, scale)   -> ('built', pid, arrays)
      ('strike', rid, sid, note, at, drv, free) -> ('free', rid, modes, z, at, floor)
                                                   [+ ('forced', rid, note, forced, at)]
      ('release', rid, sid, at, free)          -> ('free', ...)
      ('damp', rid, keys); ('stop',)"""
    import os
    try:
        os.nice(5)                     # below the audio, whose core this is not
    except OSError:
        pass
    import blockrender as B
    strings, chans = {}, {}
    while True:
        try:
            job = conn.recv()
        except EOFError:
            return
        kind = job[0]
        if kind == 'stop':
            return
        try:
            if kind == 'build':
                pid, pc, tuner, rate, scale = job[1:]
                Sg = Strings(pc, B.tuning_table(tuner), 0.0, 1.0, rate,
                             (B.string_partial, B.partial_decay, B.unison_partial))
                strings[pid] = (Sg, _isolated(pc, 261.63, 0.0, 1.0), rate, scale)
                conn.send(('built', pid, dict(M=len(Sg.f), W=Sg.W, f=Sg.f, alpha=Sg.alpha,
                                              key=Sg.key, string=Sg.string, hl=Sg.hl,
                                              hr=Sg.hr, dl=Sg.dl, dr=Sg.dr)))
                continue
            rid = job[1]
            lc = chans.get(rid)
            if lc is None and rid[0] in strings:
                Sg, props, rate, scale = strings[rid[0]]
                lc = chans[rid] = LiveChannel(Sg, props, rate, scale)
            if lc is None:
                continue
            if kind == 'strike':
                sid, note, at, drv, free = job[2:]
                idx, z, forced = lc.strike(sid, note, at, drv, free)
                conn.send(('free', rid, idx, z, at, FLOOR * max(lc.loud, 1e-30)))
                if forced:
                    conn.send(('forced', rid, note, forced, at))
            elif kind == 'release':
                sid, at, free = job[2:]
                idx, z = lc.release(sid, at, free)
                conn.send(('free', rid, idx, z, at, FLOOR * max(lc.loud, 1e-30)))
            elif kind == 'damp':
                lc.damp(job[2])
        except Exception as e:
            conn.send(('error', None, "%s: %s" % (type(e).__name__, e)))
