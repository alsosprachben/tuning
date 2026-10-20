"""THE HAMMOND SCANNER VIBRATO / CHORUS: the B-3's circuit, solved, and its
scanner as moving delays -- one model for both renderers (as siren.py and
moog.py are).

THE CIRCUIT (Werner, Dunkel & Germain, "A computational model of the Hammond
organ vibrato/chorus using wave digital filters", DAFx-16, Fig. 1 and Table 1;
~/Documents/refs/papers/werner_hammond_vibrato_dafx16): the organ's signal runs
into an LC LADDER -- L1..L18 500 mH, C1..C17 4 nF and C18 1 nF to a bottom
rail, Rt 15 k across its end -- whose taps 1-6 are voltage dividers R+/R- off
the input and the first five nodes (the early taps tapered down) and taps 7-19
the nodes after L6..L18. The bottom rail goes to ground through Rc (22 k),
which the switch SHORTS on vibrato. On chorus the line's return current lifts
the whole rail, and every tap carries the rail's voltage -- in phase with the
input, undelayed -- under its own: the chorus's DRY share, from the circuit
("part of the incoming signal appears across the vibrato line and the rest
across a resistor in series with the line", Hammond's service manual). Solved
(taps_response, AC nodal analysis): 0.71 of the input on the rail, the scanned
part ~0.3 -- not the equal mix first assumed.

THE SCANNER: a capacitive rotor turned by the organ's synchronous motor at
6.87 Hz (412 rpm; the paper rounds it to "~6 Hz") crossfades between nine
terminals t1..t9 wired to sixteen stator plates, swept t1 -> t9 -> t1 once a
revolution. Which nodes the terminals reach is the setting (the paper's Table
2): V1/C1 nodes 1-9, V2/C2 to 13, V3/C3 to 19. VIBRATO is the scanner's output
alone; CHORUS is the same with Rc in, the rail's dry share under it. One motor
turns every key's scanner: its angle is a function of absolute time.

AS ROWS AND GAINS. A crossfade between taps is, to first order, a DELAY that
moves, and a delay is a phase in proportion to each partial's own frequency --
a bend row's phase term (the kernel adds om x BC). The ladder DISPERSES (its
delay rises with frequency), so there is a row per BAND, each built from the
taps' own delays at the band's centre, and a partial rides its band's. What a
moving delay leaves out -- the ladder's lowpass and standing-wave ripple on
the scanned path, the tapered taps, the crossfade's own averaging -- is the
partial's static complex gain: the mean over a revolution of the scanned
output against its band's delay (gains). On chorus the partial itself is the
dry share (the rail's gain) and a copy the scanned.

NOT MODELLED (yet): what remains of the crossfade beyond that mean -- its
sidebands, mostly at the plate rate (16 x 6.87 = 110 Hz) and, above ~2 kHz,
the scramble two taps 134 us apart make of a partial: the scanner's grit.
"""
import math

import numpy as np

SCAN_HZ = 6.87
# the nodes each terminal t1..t9 reaches, per depth (Werner et al., Table 2)
TAPS = {1: (1, 2, 3, 4, 5, 6, 7, 8, 9),
        2: (1, 2, 3, 5, 7, 9, 11, 12, 13),
        3: (1, 2, 4, 7, 10, 13, 16, 18, 19)}
# the sixteen stator plates in turn: t1..t9 and back down to t2
PLATES = tuple(range(9)) + tuple(range(7, 0, -1))
# the dispersion's bands: each its own delay row, at these centres
BAND_HZ = (150.0, 400.0, 900.0, 1800.0, 3500.0, 7000.0)

L_H = 0.5
C_F = [0.004e-6] * 17 + [0.001e-6]
R_PLUS = (27e3, 56e3, 39e3, 33e3, 18e3, 12e3)
R_MINUS = (68e3, 150e3, 150e3, 180e3, 180e3, 180e3)
R_T = 15e3
R_C = 22e3


def parse(setting):
    """'V1'..'V3', 'C1'..'C3' -> (depth 1-3, chorus?), or None for off."""
    if not setting:
        return None
    s = str(setting).upper()
    if len(s) == 2 and s[0] in "VC" and s[1] in "123":
        return int(s[1]), s[0] == "C"
    raise ValueError("scanner setting %r: V1-V3 or C1-C3" % (setting,))


# ---------------------------------------------------------------- the circuit
def taps_response(f, chorus):
    """(rail, taps) at frequency f (Hz), each a complex ratio to the input:
    the bottom rail's voltage to ground (0 on vibrato) and the 19 tap node
    voltages to ground. AC nodal analysis: unknowns n1..n18 and the rail."""
    w = 2.0 * np.pi * f
    yL = 1.0 / (1j * w * L_H)
    yC = [1j * w * c for c in C_F]
    yD = [1.0 / (rp + rm) for rp, rm in zip(R_PLUS, R_MINUS)]   # divider k off node k-1
    N = 18
    nu = N + 1 if chorus else N
    A = np.zeros((nu, nu), complex)
    b = np.zeros(nu, complex)
    R = N

    def ysh(j):
        return yC[j - 1] + (yD[j] if j < 6 else 0.0) + (1.0 / R_T if j == N else 0.0)
    for j in range(1, N + 1):               # KCL at node j (row j-1)
        r = j - 1
        A[r, r] -= yL
        if j == 1:
            b[r] -= yL                      # n0 = vin = 1
        else:
            A[r, r - 1] += yL
        if j < N:
            A[r, r] -= yL
            A[r, r + 1] += yL
        A[r, r] -= ysh(j)
        if chorus:
            A[r, R] += ysh(j)
    if chorus:
        # the rail: every shunt's current in, divider 1 (off vin) too, Rc out
        for j in range(1, N + 1):
            A[R, j - 1] += ysh(j)
            A[R, R] -= ysh(j)
        b[R] -= yD[0]
        A[R, R] -= yD[0] + 1.0 / R_C
    x = np.linalg.solve(A, b)
    n = np.concatenate(([1.0 + 0j], x[:N]))
    rail = x[R] if chorus else 0.0 + 0j
    taps = []
    for k in range(1, 20):
        if k <= 6:
            frac = R_MINUS[k - 1] / (R_PLUS[k - 1] + R_MINUS[k - 1])
            taps.append(rail + (n[k - 1] - rail) * frac)
        else:
            taps.append(n[k - 1])
    return rail, taps


_TAB = {}


def _table(chorus):
    """The circuit on a dense log grid, 10 Hz - 24 kHz at 1/96 octave: the
    rail (complex) and each tap's rail-relative response as magnitude and
    UNWRAPPED phase, so it interpolates."""
    if chorus not in _TAB:
        fg = 10.0 * 2.0 ** (np.arange(0, int(96 * math.log2(24000 / 10.0)) + 1) / 96.0)
        rail = np.empty(len(fg), complex)
        rel = np.empty((len(fg), 19), complex)
        for i, f in enumerate(fg):
            r, t = taps_response(f, chorus)
            rail[i] = r
            rel[i] = np.asarray(t) - r
        _TAB[chorus] = (fg, rail, np.abs(rel), np.unwrap(np.angle(rel), axis=0))
    return _TAB[chorus]


def rail_at(f, chorus):
    if not chorus:
        return np.zeros(np.shape(f), complex)
    fg, rail, _m, _p = _table(chorus)
    lf = np.log(np.maximum(f, fg[0]))
    return (np.interp(lf, np.log(fg), np.abs(rail))
            * np.exp(1j * np.interp(lf, np.log(fg), np.unwrap(np.angle(rail)))))


def rel_at(f, chorus):
    """[len(f), 19] the taps' rail-relative responses at f."""
    fg, _r, mag, ph = _table(chorus)
    lf = np.log(np.maximum(np.atleast_1d(f), fg[0]))
    lg = np.log(fg)
    out = np.empty((len(lf), 19), complex)
    for k in range(19):
        out[:, k] = np.interp(lf, lg, mag[:, k]) * np.exp(1j * np.interp(lf, lg, ph[:, k]))
    return out


def tap_delays(f, chorus):
    """[19] each tap's phase delay (s) at f, rail-relative."""
    fg, _r, _m, ph = _table(chorus)
    lf = math.log(max(f, fg[0]))
    return np.array([-np.interp(lf, np.log(fg), ph[:, k]) / (2.0 * np.pi * f)
                     for k in range(19)])


# ---------------------------------------------------------------- the scanner
def crossfade(theta):
    """(terminal a, terminal b, eta) for rotor angles theta (array): the two
    plates the rotor overlaps and the share of the first."""
    p = (np.asarray(theta, float) / (2.0 * np.pi) % 1.0) * len(PLATES)
    i = np.floor(p).astype(int)
    eta = p - i
    pl = np.asarray(PLATES)
    return pl[i % len(PLATES)], pl[(i + 1) % len(PLATES)], eta


def band_of(f):
    edges = np.sqrt(np.asarray(BAND_HZ[:-1]) * np.asarray(BAND_HZ[1:]))
    return np.searchsorted(edges, np.asarray(f, float))


_DEL = {}


def band_delays(depth, band, chorus):
    """[9] the delays (s) of terminals t1..t9 at the band's centre."""
    k = (depth, band, chorus)
    if k not in _DEL:
        td = tap_delays(BAND_HZ[band], chorus)
        _DEL[k] = np.array([td[n - 1] for n in TAPS[depth]])
    return _DEL[k]


def delay(theta, depth, band, chorus):
    """The scanned delay (s) at rotor angles theta, in a band."""
    d = band_delays(depth, band, chorus)
    a, b, eta = crossfade(theta)
    return (1.0 - eta) * d[a] + eta * d[b]


def mean_delay(depth, band, chorus):
    return float(np.mean(delay(np.arange(512) * 2.0 * np.pi / 512, depth, band, chorus)))


def theta_at(t):
    return 2.0 * np.pi * SCAN_HZ * np.asarray(t, float)


def band_bc(t, depth, band, chorus, sr):
    """A band row's BC at absolute times t (s): its delay less its mean, as
    samples of phase, negated."""
    return -(delay(theta_at(t), depth, band, chorus) - mean_delay(depth, band, chorus)) * sr


def rows(nblk, blk, sr, depth, chorus):
    """[(BR, BC)] a row per band for a render nblk blocks long, from time 0:
    BC[k+1] = BC[k] + (BR[k] - 1) blk exactly."""
    t = np.arange(nblk + 1) * blk / float(sr)
    out = []
    for b in range(len(BAND_HZ)):
        bc = band_bc(t, depth, b, chorus, sr)
        out.append(((1.0 + np.diff(bc) / blk).astype(np.float32), bc[:nblk].astype(np.float64)))
    return out


_TH = np.arange(256) * 2.0 * np.pi / 256


def gains(f, depth, chorus):
    """For partials at frequencies f: (band, dry, scanned) -- the band whose row
    each rides; the dry share's complex gain (the rail's; 0 on vibrato); the
    scanned path's complex gain against that row: the mean over a revolution
    of the crossfaded taps' responses, turned back by the row's delay, and
    the row's mean delay put back in (the row carries only its motion)."""
    f = np.atleast_1d(np.asarray(f, float))
    band = band_of(f)
    dry = rail_at(f, chorus)
    rel = rel_at(f, chorus)                                  # [n, 19]
    tn = np.asarray(TAPS[depth]) - 1
    a, b, eta = crossfade(_TH)
    sc = np.empty(len(f), complex)
    for bi in np.unique(band):
        m = band == bi
        tau = delay(_TH, depth, bi, chorus)                  # [256]
        S = (1.0 - eta)[None, :] * rel[m][:, tn[a]] + eta[None, :] * rel[m][:, tn[b]]
        w = 2.0 * np.pi * f[m]
        c0 = np.mean(S * np.exp(1j * w[:, None] * tau[None, :]), axis=1)
        sc[m] = c0 * np.exp(-1j * w * mean_delay(depth, bi, chorus))
    return band, dry, sc


# THE CROSSFADE'S OWN MOTION (tier B): what the mean leaves out, as the
# Fourier series of each partial's scanned path against its band row over a
# revolution -- each component m a copy at m x SCAN_HZ, on the row, its phase
# on the motor's absolute clock. Mostly m = +-1..3 below 2 kHz (each tap's own
# gain, from the line's standing waves, wobbling the level as the scanner
# sweeps), the plate rate (m = +-16) and a scramble above 3 kHz. Only what is
# within SIDEBAND_DB of the partial's strongest component AND within FLOOR_DB
# of its note's loudest partial: measured on GM 16.8's C3, that keeps 34 copies
# a note (of 3756 at the first test alone) and 99.8% of the sidebands' energy
# -- the rest belong to partials too quiet to carry them. Live and the file
# both (Ben, A/B: "Tier B sounds better").
SIDEBANDS = True
SIDEBAND_DB = 40.0
FLOOR_DB = 60.0
MAX_SIDE = 12


def sidebands(f, depth, chorus, amp=None, note_max=None):
    """[(m array, c array)] per partial: its scanned components other than the
    mean, kept as above (amp: each partial's level; note_max: its note's
    loudest, for FLOOR_DB), phases as gains() takes the mean's."""
    f = np.atleast_1d(np.asarray(f, float))
    band = band_of(f)
    rel = rel_at(f, chorus)
    tn = np.asarray(TAPS[depth]) - 1
    M = 256
    th = np.arange(M) * 2.0 * np.pi / M
    a, b, eta = crossfade(th)
    out = [None] * len(f)
    for bi in np.unique(band):
        m_ = np.flatnonzero(band == bi)
        tau = delay(th, depth, bi, chorus)
        S = (1.0 - eta)[None, :] * rel[m_][:, tn[a]] + eta[None, :] * rel[m_][:, tn[b]]
        w = 2.0 * np.pi * f[m_]
        R = S * np.exp(1j * w[:, None] * tau[None, :])
        C = np.fft.fft(R, axis=1) / M * np.exp(-1j * w * mean_delay(depth, bi, chorus))[:, None]
        ms = np.fft.fftfreq(M, 1.0 / M).astype(int)
        for row, i in enumerate(m_):
            mag = np.abs(C[row])
            ok = (mag > mag.max() * 10.0 ** (-SIDEBAND_DB / 20.0)) & (ms != 0)
            if amp is not None and note_max is not None:
                ok &= amp[i] * mag >= note_max[i] * 10.0 ** (-FLOOR_DB / 20.0)
            keep = np.flatnonzero(ok)
            keep = keep[np.argsort(-mag[keep])][:MAX_SIDE]
            out[i] = (ms[keep], C[row][keep])
    return out


# ------------------------------------------------- the partial table, in place
def apply(cols, sel, row_of_band, depth, chorus, sr, peak=None):
    """The scanner over rows `sel` of a column dict (numpy arrays, written in
    place): on VIBRATO each becomes the scanned path on its band's row; on
    CHORUS each becomes the dry share and a COPY the scanned. Returns the
    copies (a dict of arrays, or None)."""
    if not len(sel):
        return None
    nf = np.asarray(cols['nf'], float)[sel]
    band, dry, sc = gains(nf, depth, chorus)
    rowsel = np.asarray(row_of_band)[band]

    def turned(p, g):
        return p + np.angle(g)
    side = None
    if SIDEBANDS and sr:
        side = _side_copies(cols, sel, rowsel, depth, chorus, sr, peak)
    if not chorus:
        for k in [c for c in ('aL', 'aR', 'aM') if c in cols]:
            cols[k][sel] = cols[k][sel] * np.abs(sc)
        cols['p0'][sel] = turned(cols['p0'][sel], sc)
        cols['p0R'][sel] = turned(cols['p0R'][sel], sc)
        cols['br'][sel] = rowsel
        return side
    o = {k: np.array(v[sel], copy=True) for k, v in cols.items()}
    o['_src'] = np.asarray(sel, int)          # each copy's source row
    for k in [c for c in ('aL', 'aR', 'aM') if c in cols]:
        o[k] = o[k] * np.abs(sc)
        cols[k][sel] = cols[k][sel] * np.abs(dry)
    o['p0'] = turned(o['p0'], sc)
    o['p0R'] = turned(o['p0R'], sc)
    o['br'] = rowsel.astype(o['br'].dtype)
    cols['p0'][sel] = turned(cols['p0'][sel], dry)
    cols['p0R'][sel] = turned(cols['p0R'][sel], dry)
    if side is not None:
        o = {k: np.concatenate([o[k], side[k]]) for k in o}
    return o


def note_peaks(cols, sel):
    """Each row's note's loudest partial: rows grouped by channel and onset."""
    a = np.maximum(np.abs(np.asarray(cols['aL'], float)[sel]), np.abs(np.asarray(cols['aR'], float)[sel]))
    key = np.asarray(cols['non'], float)[sel] - np.asarray(cols.get('rdl', np.zeros(len(cols['non']))), float)[sel]
    out = np.empty(len(sel))
    for k in np.unique(key):
        m = key == k
        out[m] = a[m].max()
    return a, out


def _side_copies(cols, sel, rowsel, depth, chorus, sr, peak=None):
    """Tier B's copies of rows `sel` (before they are scaled): component m of
    each at om + m x the scan's angular rate, |c| and arg c, on its band row.
    `peak`: the note's loudest partial (live: the template's), else measured."""
    nf = np.asarray(cols['nf'], float)[sel]
    amp, nmax = note_peaks(cols, sel)
    if peak is not None:
        nmax = np.full(len(sel), float(peak))
    sb = sidebands(nf, depth, chorus, amp, nmax)
    src, mm, cc = [], [], []
    for j, (ms, cs) in enumerate(sb):
        src.extend([sel[j]] * len(ms)); mm.extend(ms); cc.extend(cs)
    if not src:
        return None
    src = np.asarray(src, int); mm = np.asarray(mm, float); cc = np.asarray(cc)
    o = {k: np.array(v[src], copy=True) for k, v in cols.items()}
    dw = 2.0 * np.pi * SCAN_HZ / sr * mm
    o['om'] = o['om'] + dw
    o['nf'] = o['nf'] + SCAN_HZ * mm
    for k in [c for c in ('aL', 'aR', 'aM') if c in cols]:
        o[k] = o[k] * np.abs(cc)
    o['p0'] = o['p0'] + np.angle(cc)
    o['p0R'] = o['p0R'] + np.angle(cc)
    o['br'] = np.asarray(rowsel)[np.searchsorted(sel, src)].astype(o['br'].dtype)
    o['_src'] = src
    return o


def expand(A, channels, sr, cols=None):
    """blockrender's partial table (columns of array('d') / lists), in place:
    channels {channel: (rows per band, depth, chorus?)}. A partial already on a
    row of its own (a bend, a level row) keeps it -- the organ voices this
    serves have none. Returns the copies made."""
    if not channels or not len(A.get('om', ())):
        return 0
    keys = list(cols or A.keys())
    # copies, not views: a view of an array('d') column stops it growing
    mch = np.array(A['mch'])
    brc = np.array(A['br'])
    made = 0
    for ch, (rws, depth, chorus) in channels.items():
        sel = np.flatnonzero((mch == ch) & (brc < 0))
        if not len(sel):
            continue
        need = ('nf', 'om', 'aL', 'aR', 'aM', 'p0', 'p0R', 'br', 'non', 'rdl')
        cols = {k: np.array(A[k], float if k != 'br' else np.int64) for k in need}
        o = apply(cols, sel, rws, depth, chorus, sr)
        for k in need:
            col = A[k]
            for i in sel:
                col[int(i)] = cols[k][i]
        if o is not None:
            srcrows = o.pop('_src')
            for k in keys:
                src = o[k] if k in o else [A[k][int(i)] for i in srcrows]
                A[k].extend([x.item() if hasattr(x, 'item') else x for x in src])
            made += len(srcrows)
    return made


# ------------------------------------------------------------- the switch
# THE B-3's SELECTOR, on CC94 (GM: "Effects 4 Depth", formerly Celeste/Detune
# -- the organ's own celeste): seven positions, each a zone of the controller,
# a value at its start selecting it. 0 is off (the vibrato tablets down).
POSITIONS = (("off", 0), ("V1", 18), ("V2", 37), ("V3", 55), ("C1", 73), ("C2", 91), ("C3", 110))
SWITCH_CC = 94


def setting_from_cc(v):
    """CC94's value -> 'off', 'V1'..'C3'."""
    name = POSITIONS[0][0]
    for n, start in POSITIONS:
        if int(v) >= start:
            name = n
    return name


def setting_of(cls, cc94=None):
    """A voice's scanner setting: the channel's CC94 where the voice has the
    switch and one was sent, else the voice's own (16.8/17.8: C3), as
    parse() takes it (None: off)."""
    if getattr(cls, 'scanner_switch', False) and cc94 is not None:
        s = setting_from_cc(cc94)
        return None if s == "off" else parse(s)
    return parse(getattr(cls, 'scanner', None))
