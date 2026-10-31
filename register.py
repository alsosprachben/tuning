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
import ctypes
import math
import operator
import os
import random
import subprocess

import numpy as np

import tonelib as T

TAU = 2.0 * math.pi
KEYS = range(21, 109)            # A0..C8, the piano's 88
FLOOR = 1e-3                     # -60 dB of the strike's loudest partial
SPLIT = 1e-2                     # a change under -40 dB of a mode waits for the next
CHOIR = 16                       # a mode's string index: choir * CHOIR + its unison


def floor_of(props):
    """Where a free string's row ends, re the strike's loudest partial: FLOOR,
    or the class's register_floor_db -- a voice whose strings ring on under a
    soft note (the dulcimer's: nothing damps them, and a high note's knock
    starts its bass courses near -60) is cut while still heard at FLOOR."""
    db = getattr(props, 'register_floor_db', None)
    return FLOOR if db is None else 10.0 ** (db / 20.0)


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
        # THE CHOIRS (tonelib.HarpsichordProperties.string_choirs): a key with
        # several rows of strings has one series per row, each at its footage
        # and its own few cents (tonelib.choir_cents), decaying as its own
        # class's string does -- the same string the note loop's rank plucks.
        # A piano has one row: its unisons are strings OF that row.
        choirs = getattr(pc, 'string_choirs', None) or (("", 1.0, None),)
        # A BANK OF COURSES (tonelib.HammeredDulcimerProperties.course_keys):
        # only the pitches the instrument has strings at
        ck = getattr(pc, 'course_keys', None)
        for key in KEYS:
            if key not in table or (ck is not None and key not in ck):
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
            board = getattr(p, 'soundboard_gain', None) or p.bore_gain
            for ci, (cname, ratio, ccls) in enumerate(choirs):
                # its own class's string -- or, at another footage (the 4'), the
                # host's string at that pitch, as the rank loop builds it
                cp = (_isolated(T.rank_spectrum(ccls), f0, pan, chan_vol) if ccls is not None
                      else _isolated(T.rank_spectrum(pc), f0 * ratio, pan, chan_vol) if ratio != 1.0
                      else p)
                cr = ratio * 2.0 ** (T.choir_cents(pc, cname, key) / 1200.0) if cname else ratio
                cB = B * T.choir_stiffness(pc, cname, key) if cname else B   # its own wire
                for m in range(1, p.max_harmonic + 1):
                    hh = sp(p, f0, cr, m, cB)
                    if hh is None:
                        break
                    h, hf = hh
                    if cname:
                        hf += T.choir_partial_hz(pc, cname, key, m)
                    if hf > sr / 2:
                        break
                    if cp.harmonic_volume(m) == 0.0:
                        continue            # the note loop emits no such partial
                    dbps, logr, aftL, logrA = sa(cp, f0, m)
                    strings = [(ci * CHOIR, hf, logrA if logrA > 0 else logr)]
                    for ui, (gm, off_hz, drr, ud, uph) in enumerate(p.unison_voices(f0, m, dbps)):
                        uf, ulr = sm(hf, off_hz, drr, ud)
                        if uf <= 0 or uf > sr / 2:
                            continue
                        _, uadb = p.aftersound(f0, ud)
                        ua = math.log(T.db_ratio(uadb)) if uadb > 0 else ulr
                        strings.append((ci * CHOIR + ui + 1, uf, ua))
                    # the bridge's admittance at the mode, which couples it both ways
                    # (a piano's board; a harpsichord's body is its FormantBody)
                    w = board(hf) * p.radiation_gain(hf)
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
        # THE BRIDGES (tonelib choir_bridge): which each choir's strings cross.
        # One bridge couples directly; across bridges, through the board, at
        # cross_bridge_coupling -- the harpsichord's 4' against its 8's
        cb = getattr(pc, 'choir_bridge', None) or {}
        self.choir_bridges = np.array([cb.get(c[0], 0) for c in choirs], np.int64)
        self.bridge = self.choir_bridges[self.string // CHOIR]
        self.cross = float(getattr(pc, 'cross_bridge_coupling', 1.0))
        # A BUFFED CHOIR (tonelib buff_choirs) is its plain choir's string with
        # the pad on: one or the other answers, never both -- the buffed one
        # while its stop is drawn (it is plucked), the plain one otherwise
        # ...OR BY KEY (tonelib key_bridge: the dulcimer's bass and treble
        # bridges), and a key's PARTNER (bridge_partner: the other length of
        # its own string, past the treble bridge), coupled partner_coupling
        # times the board's
        kb = getattr(pc, 'key_bridge', None)
        self.keybridge = None
        if kb is not None:
            self.keybridge = {k: kb(p_, k) for k, p_ in self.props.items()}
            self.bridge = np.array([self.keybridge[int(k)] for k in self.key], np.int64)
        self.knock_tilt = float(getattr(pc, 'register_knock_tilt', 0.0) or 0.0)
        kp = getattr(pc, 'register_knock_profile', None)
        self.knock_profile = (np.array([q[0] for q in kp], float),
                              np.array([q[1] for q in kp], float)) if kp else None
        self.partner = dict(getattr(pc, 'bridge_partner', None) or {})
        self.partner_k = float(getattr(pc, 'partner_coupling', 1.0))
        names = [c[0] for c in choirs]
        bc = getattr(pc, 'buff_choirs', None) or {}
        self.buffs = [(names.index(b), names.index(a)) for b, a in bc.items()
                      if b in names and a in names]
        # ...and the arrays the C core reads (registercore.c strike_drive), typed
        self._c_W = np.ascontiguousarray(self.W, np.float64)
        self._c_alpha = np.ascontiguousarray(self.alpha, np.float64)
        self._c_w = np.ascontiguousarray(self.w, np.float64)
        self._c_bridge = np.ascontiguousarray(self.bridge, np.int64)
        self._c_key = np.ascontiguousarray(self.key, np.int64)
        self._c_cb = np.ascontiguousarray(self.choir_bridges, np.int64)

    def coupling(self, j, key, choir=None):
        """The bridge's weight from a driver on `key` (its choir, if any) to
        modes j: the board's admittance at each, across bridges at
        cross_bridge_coupling, and on the key's partner at partner_coupling.
        Channel and LiveChannel both ask here, so the two cannot disagree."""
        wj = self.w[j]
        if choir is not None:
            wj = wj * np.where(self.bridge[j] == self.choir_bridges[choir], 1.0, self.cross)
        elif self.keybridge is not None and key in self.keybridge:
            wj = wj * np.where(self.bridge[j] == self.keybridge[key], 1.0, self.cross)
        pk = self.partner.get(key)
        if pk is not None:
            wj = wj * np.where(self.key[j] == pk, self.partner_k, 1.0)
        return wj

    def knock_shape(self, j, key, fall):
        """The knock's level on modes j from a stroke on `key`: falling `fall`
        dB a semitone either way -- or, where the class measured it
        (register_knock_profile: (signed semitones, dB) from the struck key,
        interpolated, held past its ends), by how far above or below."""
        dk = self.key[j] - key
        prof = self.knock_profile
        g = (10.0 ** (np.interp(dk, prof[0], prof[1]) / 20.0) if prof
             else 10.0 ** (-fall * np.abs(dk) / 20.0))
        # ...AND BY EACH MODE'S FREQUENCY (register_knock_tilt): a kick gives a
        # string a velocity, and a mode's displacement goes as its velocity
        # over its frequency -- the kicked string is not as bright as a struck
        # one. 0 (every other voice): each mode alike, as it was.
        if self.knock_tilt:
            g = g * (self.f[j] / 1000.0) ** (-self.knock_tilt)
        return g

    def free_choirs(self, plucked):
        """Which choirs may answer, for a strike plucking `plucked` (None: a
        piano's, every choir one): a buffed choir while its stop is drawn,
        in place of its plain one."""
        ok = np.ones(len(self.choir_bridges), bool)
        for b, a in self.buffs:
            if plucked is not None and b in plucked:
                ok[a] = False
            else:
                ok[b] = False
        return ok


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


TBEND_CUT_SCALE = 1048576.0      # synthkernel.c: a sweep's cutoff, scaled down


def cut_time(cut):
    """A glide's cutoff as a time: a sweep (cut < 0) carries it scaled down."""
    cut = np.asarray(cut, np.float64)
    return np.where(cut < 0, -cut * TBEND_CUT_SCALE, cut)


def glide_phase(Wi, tb, tau, cut, t):
    """The kernel's tension glide, as phase added to W_i t: W_i tb tau (1 - e^{-min(t,cut)/tau});
    a NEGATIVE cut is the drum machine's sweep, f/f0 = e^{tb e^{-t/tau}}, its
    integral tau sum_k tb^k/(k k!) (1 - e^{-k t/tau}) (synthkernel.c
    tbend_integral)."""
    tb, tau, cut, t = np.broadcast_arrays(*(np.asarray(v, np.float64) for v in (tb, tau, cut, t)))
    out = Wi * tb * tau * (1.0 - np.exp(-np.minimum(t, cut_time(cut)) / tau))
    lg = cut < 0
    if np.any(lg):
        e = np.exp(-np.minimum(t, cut_time(cut)) / tau)
        acc, term, ek = np.zeros(t.shape), np.ones(t.shape), np.ones(t.shape)
        for k in range(1, 41):
            term = term * tb / k
            ek = ek * e
            acc = acc + term * (1.0 - ek) / k
        out = np.where(lg, np.asarray(Wi, np.float64) * tau * acc, out)
    return out if out.shape else float(out)


def glide_start(tb, cut):
    """The glide's start, f/f0 - 1: tb, or e^tb - 1 for a sweep (cut < 0)."""
    return np.where(np.asarray(cut) < 0, np.expm1(tb), tb)


NEAR = 30.0                      # pairs within this many glide-widths are integrated
STEP = 0.02                      # s: the glide's curvature is ~80 rad/s^2 at most
ROWS_OVER = 1.0                  # a pair's two rows at most this times its driver


def coincident(cw, Wi, bi, Wm, am):
    """The driver's decay per pair, raised where the pair COINCIDES.

    A free mode at its driver's pitch AND decay -- a harpsichord's lower 8',
    which no choir detune moves, an octave apart on a pure octave, its decay
    by absolute frequency, so G1's h2 is G2's h1 in both -- makes D -> 0, and
    the closed form's free and forced parts, c/D each, grow without bound and
    cancel to the true c t. Exactly, in the file; live places them from two
    replies a few ms apart with each its own ear gains, and a 0.1 dB miss
    between two rows 35 dB over their driver clipped (Ben: "the G an octave
    above ... sympathetic to an extreme"). So the driven part of such a pair
    decays faster by just enough that neither row outgrows the driver (cw =
    kappa * the pair's coupling, ROWS_OVER the driver's level): the sum is
    (c/D')(e^{D't} - 1), still c t until 1/(cw/ROWS_OVER) -- about 2.3 s on
    the harpsichord (cw ~0.43/s) -- and then no louder than its driver. The
    file's exact c t had grown past it: a one-way drive, no pull back on the
    string driving it, so a free string 14 dB over the one exciting it --
    289 pairs of 1.6 million in bwx15.mid's first 20 s. Every other pair: bi."""
    D = (1j * Wi - bi) - (1j * Wm - am)
    thr = np.asarray(cw, float) / ROWS_OVER
    close = np.abs(D) < thr
    # past the faster of the two, so Re D' <= -thr and |D'| >= thr: adding thr
    # to bi alone could carry a mode that decays faster than its driver
    # THROUGH zero
    return np.where(close, np.maximum(bi, am) + thr, bi), close


def _glide_grid(cut, tau):
    """Times from 0 to cut, each step STEP/2 * e^{t / 2 tau}: the linear
    exponent's error goes with the glide's curvature, which falls as
    e^{-t/tau}, so the step may grow as its square root does."""
    t = [0.0]
    while t[-1] < cut:
        t.append(min(cut, t[-1] + 0.5 * STEP * math.exp(t[-1] / (2.0 * tau))))
    return np.array(t)


# ------------------------------------------------------------------ in C
# registercore.c: free_part's arithmetic as a loop. numpy spent the time on
# small arrays -- a few dozen pairs a call, a dozen temporaries each -- not
# on the exponentials. TUNING_REGISTER_C=0 keeps the numpy path, the
# reference examples/regclose.py checks the C against (by tolerance: numpy's
# float64 exp is its own SIMD routine, so the two differ in the last bits).
_CORE = [None]


def _core():
    """The C library, built when its source is newer; False where it cannot be."""
    if _CORE[0] is None:
        _CORE[0] = False
        if os.environ.get("TUNING_REGISTER_C", "1") not in ("0", "off", ""):
            try:
                _CORE[0] = _load_core()
            except (OSError, subprocess.CalledProcessError) as e:
                print("  register: C core unavailable (%s); numpy path" % e)
    return _CORE[0]


def _load_core():
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "registercore.c")
    lib = os.path.join(here, "libregistercore.so")
    if not os.path.exists(lib) or os.path.getmtime(src) > os.path.getmtime(lib):
        # built to a temporary name and moved: a live engine and a render
        # starting at once must never load a half-written library
        tmp = "%s.%d.tmp" % (lib, os.getpid())
        # no -ffast-math, and no fused multiply-adds (numpy makes none): the
        # order of operations is the source's. The glide's integral is
        # vectorised (#pragma omp simd), its exp/expm1/sin/cos from glibc's
        # vector library, 8 wide where the machine has AVX-512
        subprocess.check_call(["gcc", "-O3", "-march=native", "-ffp-contract=off", "-fopenmp-simd",
                               "-fno-math-errno", "-mprefer-vector-width=512", "-shared", "-fPIC",
                               src, "-o", tmp, "-lmvec", "-lm"])
        os.replace(tmp, lib)
    dll = ctypes.CDLL(lib)
    P, D = ctypes.c_void_p, ctypes.c_double
    dll.free_part.argtypes = [ctypes.c_int, P, D, P, P, P, D, D, D, D, P, P]
    dll.free_part.restype = None
    dll.strike_drive.argtypes = ([ctypes.c_int] + [P] * 15 + [ctypes.c_int] + [P] * 7 + [D, ctypes.c_long,
                                 ctypes.c_long, D, D, D, D, D, D, P, P, ctypes.c_int, P, P, P, P, P])
    dll.strike_drive.restype = ctypes.c_int
    dll.dcum.argtypes = [ctypes.c_int, P, P, P, P, P, P, D, P]
    dll.dcum.restype = None
    return dll


def _free_part_c(dll, c, Wi, bi, Wm, am, tb, tau, cut, need):
    n = len(Wm)
    c = np.ascontiguousarray(np.broadcast_to(np.asarray(c, complex), (n,)))
    bi = np.ascontiguousarray(np.broadcast_to(np.asarray(bi, float), (n,)))
    Wm = np.ascontiguousarray(Wm, float)
    am = np.ascontiguousarray(am, float)
    fr = np.empty(n, complex)
    fo = np.empty(n, complex)
    dll.free_part(n, c.ctypes.data, float(Wi), bi.ctypes.data, Wm.ctypes.data, am.ctypes.data,
                  float(tb), float(tau), float(cut), float(need), fr.ctypes.data, fo.ctypes.data)
    return fr, fo


def free_part(c, Wi, bi, Wm, am, tb=0.0, tau=1.0, cut=0.0, need=0.0):
    """free_part_py's answer, from the C core where it is built and the call
    is one driver partial on an array of modes (as Channel and LiveChannel
    make it); else free_part_py's own."""
    dll = _core()
    if (dll and np.ndim(Wm) == 1 and len(Wm)
            and np.ndim(Wi) == np.ndim(tb) == np.ndim(tau) == np.ndim(cut) == 0):
        return _free_part_c(dll, c, Wi, bi, Wm, am, tb, tau, cut, need)
    return free_part_py(c, Wi, bi, Wm, am, tb, tau, cut, need)


def free_part_py(c, Wi, bi, Wm, am, tb=0.0, tau=1.0, cut=0.0, need=0.0):
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
    D0 = (1j * Wi * (1.0 + glide_start(tb, cut)) - bi) - (1j * Wm - am)
    free = -c / D0
    width = np.abs(Wi * glide_start(tb, cut)) + np.abs(am - bi) + 1.0
    # integrated where the glide matters AND the answer can reach `need` (a
    # pair whose whole response is under it has an adiabatic error under it too)
    near = (tb != 0) & (np.abs(Wi - Wm) < NEAR * width) & (np.abs(free) >= need)
    if np.any(near):
        wi, wm, b_, a_, cc = Wi[near], Wm[near], bi[near], am[near], c[near]
        tb_, ta_, cu_ = tb[near], tau[near], cut[near]
        ca_ = cut_time(cu_)             # the cut as a time; its sign is the shape
        # one grid for all (the glide's settle time and cut are the strike's)
        grid = _glide_grid(float(ca_.max()), float(ta_.max()))

        def integral(tt):
            tt = tt[:, None] * np.ones_like(ca_)[None, :]
            tt = np.minimum(tt, ca_[None, :])
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
        th = glide_phase(wi, tb_, ta_, cu_, ca_)
        free[near] = y - forced[near] * np.exp(1j * th + (1j * (wi - wm) + (a_ - b_)) * ca_)
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

    def __init__(self, ch, strings, props, pedal, sr, blk, cols, scale=1.0, keep=True, damping=None):
        self.ch, self.S, self.sr, self.blk, self.cols = ch, strings, sr, blk, cols
        self.keep = keep             # keep each strike's driver rows once used (the
                                     # whole table, which holds every row anyway)
        P = props
        self.kappa = float(getattr(P, 'register_gain', 0.0)) * scale
        self.knock = float(getattr(P, 'register_knock_gain', 0.0)) * scale
        self.fall = float(getattr(P, 'register_knock_falloff', 0.0))
        self.top = int(getattr(P, 'damper_top', 128))
        self.fl = floor_of(P)
        self.rel = float(getattr(P, 'release_valve_time', 0.12) or 0.12) * sr
        # the pedal's free spans, (s, s) -- or, a HALF-PEDALLED channel
        # (damper.py), a function of the key giving that key's: free until its
        # damper's contact is full. A sympathetic string rings far under the
        # felt's gap, so through the band it is free (Lehtonen's level limit)
        self.pedal_of = pedal if callable(pedal) else None
        self.pedal = [] if callable(pedal) else [(a * sr, b * sr) for a, b in pedal]
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
        # THE FELT IN THE BAND (damper.py, half-pedalling): a free string
        # under a damper that only touches it loses energy to it all the same
        # -- the residual, the highs first. damping(key) -> (breakpoints in
        # samples, the extra rate from each, nepers/s at the key's own
        # fundamental), or None for a key never in the band. The state decays
        # by it, each row is written with the rate at its start, and a pedal
        # move that changes a key's rate re-segments that key's strings.
        self.r_lr = np.array(strings.alpha, float)      # each mode's row rate
        self.damp = {}
        self.pevents = {}            # block -> keys whose rate changes there
        self.dw = None
        if damping is not None:
            f0 = 440.0 * 2.0 ** ((np.asarray(strings.key, float) - 69.0) / 12.0)
            import damper as _DMP
            self.dw = (np.maximum(np.asarray(strings.f, float), 1e-6) / f0) ** _DMP.BETA
            for k in self.keyidx:
                got = damping(k)
                if got is None:
                    continue
                bk, rate = np.asarray(got[0], float), np.asarray(got[1], float)
                if not len(bk) or not np.any(rate):
                    continue
                D = np.concatenate(([0.0], np.cumsum(rate[:-1] * np.diff(bk) / sr)))
                self.damp[k] = (bk, rate, D)
                for i in range(len(bk)):
                    if i == 0 or rate[i] != rate[i - 1]:
                        b = int(math.ceil(bk[i] / blk)) * blk
                        self.pevents.setdefault(b, set()).add(k)
        # ...and the same tables flat, each key a slice, for the C core's dcum
        self._dflat = None
        if self.damp:
            off = np.zeros(130, np.int64)
            parts = [self.damp.get(k) for k in range(129)]
            for k in range(129):
                off[k + 1] = off[k] + (len(parts[k][0]) if parts[k] is not None else 0)
            cat = lambda i: np.ascontiguousarray(np.concatenate(                 # noqa: E731
                [p_[i] for p_ in parts if p_ is not None]), np.float64)
            self._dflat = (off, cat(0), cat(1), cat(2))

    def _drate(self, keys, n):
        """The felt's extra rate (nepers/s at the key's fundamental) at sample
        n, for each of these modes' keys."""
        out = np.zeros(len(keys))
        for k in np.unique(keys):
            d = self.damp.get(int(k))
            if d is not None:
                i = int(np.searchsorted(d[0], n, 'right')) - 1
                if i >= 0:
                    out[keys == k] = d[1][i]
        return out

    def _dcum(self, keys, n):
        """The felt's damping done by n (nepers at the key's fundamental)."""
        dll = _core()
        if dll and self._dflat is not None and len(keys):
            # in C (registercore.c dcum): the same arithmetic, bit-identical
            off, bk, rate, D = self._dflat
            k8 = np.ascontiguousarray(keys, np.int64)
            t8 = np.ascontiguousarray(np.broadcast_to(np.asarray(n, float), (len(keys),)), np.float64)
            out = np.empty(len(keys))
            dll.dcum(len(keys), k8.ctypes.data, t8.ctypes.data, off.ctypes.data, bk.ctypes.data,
                     rate.ctypes.data, D.ctypes.data, float(self.sr), out.ctypes.data)
            return out
        out = np.zeros(len(keys))
        if self.damp:
            n = np.broadcast_to(np.asarray(n, float), (len(keys),))
            for k in np.unique(keys):
                d = self.damp.get(int(k))
                if d is not None:
                    m = keys == k
                    i = np.searchsorted(d[0], n[m], 'right') - 1
                    j = np.maximum(i, 0)
                    out[m] = np.where(i >= 0, d[2][j] + d[1][j] * (n[m] - d[0][j]) / self.sr, 0.0)
        return out

    def _dgain(self, modes, n0, n1):
        """exp(-felt) on these modes from n0 to n1: 1 where nothing damps."""
        if not self.damp or not len(modes):
            return 1.0
        keys = self.S.key[modes]
        return np.exp(-self.dw[modes] * (self._dcum(keys, n1) - self._dcum(keys, n0)))

    # -- the free spans, as known ----------------------------------------------
    def _span_list(self, key):
        sp = self.spans.get(key)
        if sp is None:
            if key >= self.top:
                sp = [(0.0, float('inf'))]
            else:
                ped = (self.pedal if self.pedal_of is None
                       else [(a * self.sr, b * self.sr) for a, b in self.pedal_of(key)])
                sp = _merge(ped + self.holds.get(key, []))
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
        return self.fl * max(self.loud, 1e-30)

    # -- strikes in -----------------------------------------------------------
    def strike(self, key, on, held, av, rows, plucked=None, choirs=None):
        """A strike: its key, onset and the time its key came up (s), and its
        rows as {column: array} -- every column, the whole note. `plucked`:
        the choirs it plucked (Strings' choir indices); None, every string of
        the key -- a piano's hammer strikes them all. On a harpsichord the
        key's other choirs are undamped and free while it is down. `choirs`:
        each row's choir (Strings' index), for its bridge; None, all one."""
        sr, blk = self.sr, self.blk
        d = np.flatnonzero(np.asarray(rows['dr']) > 0.5)
        # ITS OWN KEY'S FREE CHOIRS ARE FREE FROM ITS BLOCK. The strike is
        # worked at the block its partials start in, which begins up to a
        # block before the key goes down; a hold from the key-down left the
        # key's undrawn choirs damped at that instant, and their free part
        # was dropped -- only the forced part, at the plucked string's own
        # pitch, ever sounded. (A piano strikes every string of its key, and
        # its holds stay where they were.)
        n_on = on * sr
        if plucked is not None and len(d):
            n_on = min(n_on, int(float(np.asarray(rows['non'])[d].min()) // blk) * blk)
        self.holds.setdefault(key, []).append((n_on, held * sr))
        self.spans.pop(key, None)
        self.endmemo.pop(key, None)
        if not len(d):
            return
        si = len(self.strikes)
        drv = {c: np.asarray(rows[c])[d] for c in self.cols}
        self.strikes.append(dict(key=key, av=av, drv=drv, plucked=plucked,
                                 choir=None if choirs is None else np.asarray(choirs)[d]))
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
            # (a pedal move as a strike: once its block is done, so the stream
            # meets it after the same strikes the whole table does)
            eb = min((p for p in self.pevents if p + blk <= T), default=None)
            if gb is None and pb is None and eb is None:
                break
            if eb is not None and (gb is None or eb < gb) and (pb is None or eb < pb):
                # THE PEDAL MOVED: these keys' sounding strings take their new
                # rate from here (a row a rate, crossed over as a split is)
                keys = self.pevents.pop(eb)
                mk = np.isin(self.S.key, list(keys)) & (self.Az != 0)
                if mk.any():
                    self._update(mk, eb, np.zeros(len(self.Az), complex), ('pedal', eb), force=mk)
                continue
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
        if self.pevents:
            e = min(e, min(self.pevents))
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
            okc = S.free_choirs(st['plucked'])[S.string // CHOIR]
            for k, ix in self.keyidx.items():
                if k != st['key']:
                    if self.span_end(k, b) is not None:
                        free[ix[okc[ix]]] = True
                elif st['plucked'] is not None and self.span_end(k, b) is not None:
                    # its own key: every choir but the plucked ones
                    free[ix[okc[ix] & ~np.isin(S.string[ix] // CHOIR, list(st['plucked']))]] = True
            if not free.any():
                continue
            fi = np.flatnonzero(free)
            fW = Wm[fi]
            xfer = np.zeros(M, complex)
            n_off = None
            dll = _core()
            if dll:
                # the loop below, in C (registercore.c strike_drive)
                n_off, re_off = self._drive_c(dll, drv, st, fi, b, floor, add, xfer, si)
            else:
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
                        wj = S.coupling(j, st['key'], None if st['choir'] is None else st['choir'][r])
                        bj, close = coincident(self.kappa * wgt * wj, Wi, beta, Wm[j], am[j])
                        fr, fo = free_part(cmax * wj, Wi, bj, Wm[j], am[j], tb, ta, cu,
                                           need=floor * SPLIT)
                        # free: from the driver's onset, at the mode's own frequency
                        add[j] += fr * np.exp(1j * (theta - Wm[j] * n_i / sr) + am[j] * (n_i - b) / sr)
                        # forced: one row riding this driver's stage, relative to it --
                        # and one more for each coincident pair, at its own decay
                        F = complex(fo[~close].sum())
                        if abs(F) > floor * SPLIT:
                            self._forced(drv, r, beta, F / a_i, si)
                        for k in np.flatnonzero(close):
                            if abs(fo[k]) > floor * SPLIT:
                                self._forced(drv, r, float(bj[k]), complex(fo[k]) / a_i, si)
                        # what the forced part holds when this driver's damper falls
                        tq = (n_off - n_i) / sr
                        gq = glide_phase(Wi, tb, ta, cu, tq)
                        xfer[j] += fo * np.exp(1j * (theta + Wi * tq + gq - Wm[j] * n_off / sr)
                                               - bj * tq)
            if self.knock > 0:
                # through the bridge as the drive is: across bridges, and onto
                # the struck string's own other length (S.coupling)
                amp = self.knock * float(np.max(drv['aM'])) * S.coupling(fi, st['key']) \
                    * S.knock_shape(fi, st['key'], self.fall)
                add[fi] += amp * np.exp(1j * knock_phase(hash((self.ch, si)), len(fi)))
            if n_off is not None and np.any(xfer):
                pb = int(math.ceil((n_off + re_off) / blk)) * blk
                cand = np.flatnonzero(np.abs(xfer) >= floor)
                if len(cand):
                    seqs = list(range(self.seq, self.seq + len(cand)))
                    self.seq += len(cand)
                    self.bridges.append((seqs, cand, xfer[cand], n_off, re_off, pb, ('damper', si)))
                tr = xfer * np.exp(-am * (pb - n_off) / sr) * self._dgain(np.arange(M), n_off, pb)
                self.pending[pb] = self.pending[pb] + tr if pb in self.pending else tr
        self._update(np.abs(add) > 0, b, add, ('strike', b))

    def _drive_c(self, dll, drv, st, fi, b, floor, add, xfer, si):
        """_strikes' loop over one strike's driver partials, in C: adds each
        mode's free kick to `add` and its damper hand-over to `xfer`, makes
        the forced rows in the Python's order, and returns the last driver's
        (noff, re) -- (None, None) if none was over the floor."""
        S, M = self.S, len(self.S.f)
        if not hasattr(S, '_c_W'):          # a Strings made before the core read them
            S._c_W, S._c_alpha, S._c_w = (np.ascontiguousarray(v, np.float64) for v in (S.W, S.alpha, S.w))
            S._c_bridge, S._c_key, S._c_cb = (np.ascontiguousarray(v, np.int64)
                                              for v in (S.bridge, S.key, S.choir_bridges))
        f8 = lambda v: np.ascontiguousarray(v, np.float64)          # noqa: E731
        i8 = lambda v: np.ascontiguousarray(v, np.int64)            # noqa: E731
        R = len(drv['om'])
        cols = [f8(drv[c]) for c in ('aM', 'om', 'non', 'p0', 'delL', 'noff', 're', 'tbav', 'tau',
                                       'tcut', 'aft', 'sus', 'logr', 'logrA')]
        choir = i8(np.full(R, -1) if st['choir'] is None else st['choir'])
        key = st['key']
        kb = S.keybridge[key] if S.keybridge is not None and key in S.keybridge else -1
        pk = S.partner.get(key)
        fi8 = i8(fi)
        cap = 4 * 3 * max(R, 1)
        while True:
            add_s = np.zeros(M, complex)
            xfer_s = np.zeros(M, complex)
            f_r = np.zeros(cap, np.int32)
            f_beta = np.zeros(cap, np.float64)
            f_val = np.zeros(cap, complex)
            lo_ = ctypes.c_double()
            lr_ = ctypes.c_double()
            n = dll.strike_drive(R, *[c.ctypes.data for c in cols], choir.ctypes.data,
                                 len(fi8), fi8.ctypes.data, S._c_W.ctypes.data, S._c_alpha.ctypes.data,
                                 S._c_w.ctypes.data, S._c_bridge.ctypes.data, S._c_key.ctypes.data,
                                 S._c_cb.ctypes.data, float(S.cross), int(kb),
                                 int(-1 if pk is None else pk), float(S.partner_k),
                                 float(self.kappa), float(floor), SPLIT, float(self.sr), float(b),
                                 add_s.ctypes.data, xfer_s.ctypes.data, cap,
                                 f_r.ctypes.data, f_beta.ctypes.data, f_val.ctypes.data,
                                 ctypes.byref(lo_), ctypes.byref(lr_))
            if n <= cap:
                break
            cap = n
        add += add_s
        xfer += xfer_s
        for k in range(n):
            self._forced(drv, int(f_r[k]), float(f_beta[k]), complex(f_val[k]), si)
        if lo_.value < 0:
            return None, None
        return lo_.value, lr_.value

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

    def _update(self, m, b, add, src, force=None):
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
        Az[idx] = (Az[idx] * np.exp(-am[idx] * np.maximum(b - nref[idx], 0.0) / sr)
                   * self._dgain(idx, nref[idx], b) + add[idx])
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
            rz[has] = np.where(alive, self.Rz[h] * np.exp(-self.r_lr[h] * np.maximum(b - self.rref[h], 0.0) / sr), 0)
        mag = np.maximum(np.abs(tz), floor)
        go = np.abs(tz - rz) > SPLIT * mag
        if force is not None:
            go |= force[idx] & has
        go = idx[go]
        if not len(go):
            return
        free_now = ~np.isnan(self.ends(S.key[go], np.full(len(go), float(b))))
        # the felt's rate at b, asked once for all of them (a lookup: the same
        # values as asking mode by mode, which was most of _update's time)
        drate = self._drate(S.key[go], float(b)) if self.damp else None
        for k_, (i, fr) in enumerate(zip(go, free_now)):
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
            lr = float(am[i]) + (float(self.dw[i] * drate[k_]) if self.damp else 0.0)
            n_floor = b + sr * math.log(abs(z) / floor) / max(lr, 1e-9)
            rec = self._write(i, z, b, self.blk, None, None, 'free', src, lr=lr)
            rec.update(mode=i, b=float(b), key=int(S.key[i]), n_floor=n_floor, closed=None)
            self.open.append(rec)
            self.rrec[i] = rec
            self.has[i] = True
            self.r_b[i] = b; self.r_nfloor[i] = n_floor; self.r_closed[i] = np.inf
            self.Rz[i] = z; self.rref[i] = b; self.r_lr[i] = lr

    def _alive(self, rec, b):
        """Whether a free row still sounds at b, as far as it can be known."""
        end = self.span_end(rec['key'], rec['b'])
        x = min(rec['n_floor'], end if end is not None else rec['b'])
        if rec['closed'] is not None:
            x = min(x, rec['closed'])
        return x > b

    # a free row's fields that are the same on every row
    _CONST = dict(logrA=0.0, aft=0.0, sus=0.0, cv=0.0, sj=0.0, crl=0.0, csc=0.0, cbw=0.0, tbav=0.0,
                  tcut=0.0, gb=0.0, gc=0.0, vd=0.0, vdl=0.0, br=-1, gr=-1, cr=0,
                  fx=-1, mk=0, rdl=0.0, fmw=0.0, fmp=0.0, fmpR=0.0, dr=1.0)

    def _write(self, i, z, non, fa, noff, re_, kind, src, seq=None, lr=None):
        S, sr = self.S, self.sr
        om = S.W[i] / sr
        ph = math.atan2(z.imag, z.real)
        # the template with the constant fields, made once a template
        if getattr(self, '_base_of', None) is not self.template:
            self._base = dict(self.template)
            self._base.update(self._CONST)
            self._base_of = self.template
        row = dict(self._base)
        row.update(om=om, p0=ph - om * S.dl[i], p0R=ph - om * S.dr[i],
                   aL=abs(z) * S.hl[i], aR=abs(z) * S.hr[i], aM=abs(z),
                   nf=S.f[i], nfr=S.f[i], non=float(non), noff=noff,
                   fa=float(fa), re=re_, logr=float(S.alpha[i] if lr is None else lr),
                   delL=S.dl[i], delR=S.dr[i], px=S.px[i], pl=int(S.string[i]))
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
    return Channel(ch, S, R['props'], R['pedal'], sr, blk, cols, scale, keep, R.get('damping'))


# array-module typecodes the table's columns use, as numpy dtypes
_ARRAY_DTYPE = {'f': np.float32, 'd': np.float64, 'i': np.int32}


def expand(A, channels, sr, blk, cols, meta=None):
    """The whole table's way: every register channel fed all its strikes,
    finished, its rows appended in (phase, seq) order -- the order the
    stream's keys put them in. channels: {ch: Channel, with its strikes fed}.
    Returns the number of rows added."""
    added = 0
    for ch, C in channels.items():
        C.finish()
        recs = sorted(C.take(), key=lambda r: (r['phase'], r['seq']))
        rows = [r['row'] for r in recs]
        for c in cols:
            col = A[c]
            vals = list(map(operator.itemgetter(c), rows))
            nd = _ARRAY_DTYPE.get(getattr(col, 'typecode', None))
            if nd is not None and vals:
                # a typed column takes the whole run as bytes: numpy casts as
                # the array module does (float64 -> float32 rounds to nearest)
                col.frombytes(np.asarray(vals).astype(nd).tobytes())
            else:
                col.extend(vals)
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
        self.fl = floor_of(P)
        M = len(strings.f)
        self.keyidx = {k: np.flatnonzero(strings.key == k) for k in strings.props}
        self.Az = np.zeros(M, complex); self.nref = np.zeros(M)
        self.Rz = np.zeros(M, complex); self.rref = np.zeros(M)    # what is stamped
        self.stamped = np.zeros(M, bool)
        self.held = {}               # strike id -> its forced parts, for the hand-over
        self.loud = 0.0
        # THE FELT IN THE BAND (damper.py; Channel's damping): each mode's
        # extra rate now, nepers/s, set by felt(); and the rate its stamped
        # row was written with
        self.krate = np.zeros(M)
        self.Rk = np.zeros(M)
        import damper as _DMP
        f0 = 440.0 * 2.0 ** ((np.asarray(strings.key, float) - 69.0) / 12.0)
        self.dw = (np.maximum(np.asarray(strings.f, float), 1e-6) / f0) ** _DMP.BETA

    def mask(self, keys):
        m = np.zeros(len(self.S.f), bool)
        for k in keys:
            ix = self.keyidx.get(k)
            if ix is not None:
                m[ix] = True
        return m

    def _settle(self, touched, at, force=None):
        """The touched modes whose stamped row has drifted: (modes, Z at `at`)."""
        am, sr = self.S.alpha, self.sr
        idx = np.flatnonzero(touched)
        if not len(idx):
            return idx, np.zeros(0, complex)
        tz = self.Az[idx]
        rz = np.where(self.stamped[idx],
                      self.Rz[idx] * np.exp(-(am[idx] + self.Rk[idx]) * np.maximum(at - self.rref[idx], 0.0) / sr), 0)
        floor = self.fl * max(self.loud, 1e-30)
        go = np.abs(tz - rz) > SPLIT * np.maximum(np.abs(tz), floor)
        if force is not None:
            go |= force
        idx, z = idx[go], tz[go]
        self.Rz[idx] = z; self.rref[idx] = at; self.Rk[idx] = self.krate[idx]
        self.stamped[idx] = np.abs(z) >= floor
        return idx, z

    def strike(self, sid, key, at, drv, free_keys, plucked=None):
        """A strike at sample `at` of `key`, its stamped direct rows `drv`
        ({om, p0, delL, aM, non, logr, logrA, aft, sus, tbav, tau, tcut, slot}),
        with these keys' strings free. `plucked`, as Channel.strike's: the
        choirs it plucked; its key's others are free while it is held."""
        S, sr = self.S, self.sr
        Wm, am = S.W, S.alpha
        M = len(S.f)
        free = self.mask(k for k in free_keys if k != key)
        if plucked is not None and key in free_keys and key in self.keyidx:
            ix = self.keyidx[key]
            free[ix[~np.isin(S.string[ix] // CHOIR, list(plucked))]] = True
        free &= S.free_choirs(plucked)[S.string // CHOIR]     # a buff's string, or its plain one
        self.loud = max(self.loud, float(np.max(drv['aM'])) if len(drv['aM']) else 0.0)
        floor = self.fl * max(self.loud, 1e-30)
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
                    wj = S.coupling(j, key, int(drv['choir'][r]) if 'choir' in drv else None)
                    bj, close = coincident(self.kappa * wgt * wj, Wi, beta, Wm[j], am[j])
                    fr, fo = free_part(cmax * wj, Wi, bj, Wm[j], am[j], tb, ta, cu,
                                       need=floor * SPLIT)
                    add[j] += fr * np.exp(1j * (theta - Wm[j] * n_i / sr) + am[j] * (n_i - at) / sr)
                    # as Channel.strike: a coincident pair's forced part its own row
                    F = complex(fo[~close].sum())
                    if abs(F) > floor * SPLIT:
                        forced.append((int(drv['slot'][r]), wgt, beta, F / a_i))
                    for k in np.flatnonzero(close):
                        if abs(fo[k]) > floor * SPLIT:
                            forced.append((int(drv['slot'][r]), wgt, float(bj[k]), complex(fo[k]) / a_i))
                    keep.append((j, fo, Wi, bj, theta, n_i, tb, ta, cu))
        if self.knock > 0 and len(fi):
            amp = self.knock * self.loud_of(drv) * S.coupling(fi, key) * S.knock_shape(fi, key, self.fall)
            add[fi] += amp * np.exp(1j * knock_phase(hash(('live', sid)), len(fi)))
        self.held[sid] = keep
        touched = np.abs(add) > 0
        self.Az[touched] = self.Az[touched] * np.exp(
            -(am[touched] + self.krate[touched]) * np.maximum(at - self.nref[touched], 0.0) / sr) + add[touched]
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
            -(am[touched] + self.krate[touched]) * np.maximum(at - self.nref[touched], 0.0) / sr) + add[touched]
        self.nref[touched] = at
        return self._settle(touched, at)

    def damp(self, keys):
        """These keys' dampers fell: their strings are at rest."""
        m = self.mask(keys)
        self.Az[m] = 0; self.Rz[m] = 0; self.stamped[m] = False

    def felt(self, at, keys, rates):
        """The pedal moved at sample `at`: these keys' strings decay from here
        at their own rate plus the felt's (rates: nepers/s at each key's
        fundamental, the highs more). Their sounding modes are brought to
        `at` and re-stamped at the new rate: (modes, Z at `at`)."""
        S, am, sr = self.S, self.S.alpha, self.sr
        new = self.krate.copy()
        for k, r in zip(keys, rates):
            ix = self.keyidx.get(k)
            if ix is not None:
                new[ix] = r * self.dw[ix]
        ch = np.flatnonzero(new != self.krate)
        live = ch[self.Az[ch] != 0]
        self.Az[live] *= np.exp(-(am[live] + self.krate[live]) * np.maximum(at - self.nref[live], 0.0) / sr)
        self.nref[live] = at
        self.krate = new
        touched = np.zeros(len(S.f), bool); touched[live] = True
        return self._settle(touched, at, force=touched[np.flatnonzero(touched)])


def live_worker(conn):
    """live.py's register worker, in a PROCESS of its own: the response is
    Python-heavy, and a thread doing it took the interpreter lock from the
    audio callback (a pedal-up block went 1.9 -> 6.7 ms against a 2.67 ms
    budget). Jobs in, results out, over a pipe:

      ('build', pid, pc, tuner, rate, scale)   -> ('built', pid, arrays)
      ('strike', rid, sid, note, at, drv, free[, plucked]) -> ('free', rid, modes, z, at, floor)
                                                   [+ ('forced', rid, note, forced, at)]
      ('release', rid, sid, at, free)          -> ('free', ...)
      ('damp', rid, keys); ('stop',)
      ('felt', rid, at, keys, rates)           -> ('free', ...): the pedal in the band"""
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
                sid, note, at, drv, free = job[2:7]
                idx, z, forced = lc.strike(sid, note, at, drv, free, job[7] if len(job) > 7 else None)
                conn.send(('free', rid, idx, z, at, lc.fl * max(lc.loud, 1e-30)))
                if forced:
                    conn.send(('forced', rid, note, forced, at))
            elif kind == 'release':
                sid, at, free = job[2:]
                idx, z = lc.release(sid, at, free)
                conn.send(('free', rid, idx, z, at, lc.fl * max(lc.loud, 1e-30)))
            elif kind == 'damp':
                lc.damp(job[2])
            elif kind == 'felt':
                at, keys, rates = job[2:5]
                idx, z = lc.felt(at, keys, rates)
                if len(idx):
                    conn.send(('free', rid, idx, z, at, lc.fl * max(lc.loud, 1e-30)))
        except Exception as e:
            conn.send(('error', None, "%s: %s" % (type(e).__name__, e)))
