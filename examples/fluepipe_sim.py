#!/usr/bin/env python3
"""A FLUE PIPE FROM ITS CONSTRUCTION: the jet, the lip, the pipe's modes --
for the pipe organ's flue stops, off the Piteå recordings (2026-11-24, the
harmonium's way: examples/freereed_sim.py). Nothing here is fitted to a
recording; dimensions are Audsley's (organ_notes), the acoustics the
literature's, and what neither gives is a named variable for Ben's ear.

    python3 examples/fluepipe_sim.py --survey [STOP]      tone and speech at C2..C6
    python3 examples/fluepipe_sim.py --wav OUT.wav [STOP] [KEY]

THE MODEL (the jet-drive model: Fletcher, JASA 60 1976; Verge, Fabre,
Hirschberg et al., JASA 95/101 1994-97; as Auvray, Fabre & Lagrée run it in
the time domain, JASA 131 2012):

  the jet     leaves the flue (height h) at Uj = sqrt(2 p / rho), p the foot
              pressure. A transverse acoustic velocity v at the flue exit is
              carried to the upper lip at cp = JET_CP x Uj -- a delay tau =
              W / cp over the cut-up W -- growing as e^(mu W), mu = JET_MU / h:
              eta(t) = (h / Uj) e^(mu W) v(t - tau)
  the lip     splits the jet (Bickley profile, half-width b = 2h/5) into the
              pipe and out: Qin = B b Uj (1 + tanh((eta - y0) / b)), B the
              mouth width, y0 the lip's offset from the jet's centre
  the drive   the jet's flow injected at the lip acts as a pressure across
              the mouth: dp = (rho delta_d / (B W)) dQin/dt (its sign, in our
              flow convention, the one loop_gain shows starts the pipe), delta_d =
              (4 / pi) sqrt(2 h W) (Verge's dipole distance)
  the loss    vortex shedding at the lip: -(rho / 2) (v / ALPHA_VC)^2 sign v
  the pipe    its loop admittance Y(w) = 1 / (Z_pipe + Z_mouth), worked out
              from the dimensions in the FREQUENCY domain (examples/pipe_
              impedance.py: Keefe's wall losses, Levine-Schwinger radiation,
              stopped / chimney / conical bores), then broken into its MODES
              -- each a frequency, a Q and a weight, a complex one-pole
              stepped exactly -- so the time domain has only what truly
              evolves: the jet's delay and the lip's nonlinearity.

The mouth flow Q is the modes' sum; v = Q / (B W). What radiates is dQ/dt at
the mouth and, at an open pipe's far end, the end's own flow (each mode's
end/mouth ratio from the transmission matrix): their powers added, as a
listener away from both hears them. The foot fills through the pallet and
the toe hole over FOOT_RISE_S (key velocity: PALLET_*), and the jet's own
turbulence (TURB_REL of its flow, band-limited by the jet's own scale) is the
pipe's wind noise and, with the upper modes winning the first race, its chiff.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipe_impedance as PI  # noqa: E402

RHO, C = PI.RHO, PI.C
SR = 96000                    # the jet's delay wants fine time; decimated by 2 for analysis
JET_CP = 0.40                 # the jet's disturbance speed over Uj (Fletcher; Verge: 0.3-0.5)
JET_MU = 0.40                 # its spatial growth, x 1/h (Auvray et al. 2012, 0.4 / h)
JET_SPREAD = 0.05             # its half-width's growth per metre travelled (Fletcher)
JET_EXP_MAX = 5.0             # the growth's ceiling, e^this
ETA_SAT = 3.0                 # (Ben's voicing A, 2026-11-24) the jet's amplitude saturation: its swing at the lip at most ~this x its half-width (0 = none)
ALPHA_VC = 0.6                # the vena contracta of the flow round the lip (Auvray)
TURB_REL = 0.02               # the jet's turbulence, rms over its mean flow (named: by ear)
FOOT_RISE_S = 0.012           # the foot's fill once the pallet is open (named: by ear)
PALLET_GENTLE_S, PALLET_SHARP_S = 0.015, 0.004     # the pallet's opening, gentle to sharp key
LIP_THICK_M = 0.0005          # the upper lip's thickness (metal) -- its inertance
MAX_HZ = 16000.0              # the highest mode kept
JET_PHASE_MAX = 1.9           # the jet's transit at most this many radians of the period (the voicer's cut)
VOICE_REF_HZ = 261.63          # where a stop's own cut-up ratio holds; above it the jet keeps its timing
MIN_Q = 4.0                   # a resonance, not the radiation's slope


# ---- a stop's construction (Audsley; organ_notes.md) -----------------------
# scale     diameter of C (8' C, 65.4 Hz written) in m, and the halving
#           interval in semitones (Normalmensur: the diameter halves on the
#           17th note, 16 semitones up)
# mouth     width as a fraction of the circumference
# cutup     the mouth's height as a fraction of its width
# flue      the flue's height h as a fraction of the diameter
# pressure  foot pressure, Pa
# end       "open", "stopped", "chimney" (chimney length, radius over the
#           body's), "conical" (top radius over the mouth's)
STOPS = {
    # Audsley's Major Principal (OTC p.491-492): CC 6.16 in, halving on the
    # 18th pipe (1:2.66), mouth 1/4 C, cut-up 1/4 D (~0.32 W), 3-5 in of wind
    # (3.5 in = 870 Pa); the flue's height he will not tabulate (named)
    "principal": dict(d_c=0.1565, halve=17, mouth=0.25, cutup=0.32, flue=0.015, pressure=870.0, end="open",
                      offset=1.0),
    # the rest of the chorus (OTC spec p.491-494; d_c is the diameter the
    # scale gives at 65.4 Hz, worked back from the stop's own CC pipe):
    # Major Octave CC (4' pipe) 3.48 in on 2.66
    "octave": dict(d_c=0.0884 * 2 ** (12 / 17.0), halve=17, mouth=0.25, cutup=0.32, flue=0.015, pressure=870.0,
                   end="open", offset=1.0),
    # Super-Octave CC (2' pipe) 1.91 in on 2.3 (halving on the 21st pipe)
    "superoctave": dict(d_c=0.0485 * 2 ** (24 / 20.0), halve=20, mouth=0.25, cutup=0.32, flue=0.015,
                        pressure=870.0, end="open", offset=1.0),
    # Octave Quint 2 2/3 CC (G 196 Hz pipe) 2.41 in on 2.66
    "quint": dict(d_c=0.0612 * 2 ** (19 / 17.0), halve=17, mouth=0.25, cutup=0.32, flue=0.015, pressure=870.0,
                  end="open", offset=1.0),
    # Double Principal 16: its C (8' pipe) 6.16 in, as the unison's, on 2.66
    "principal16": dict(d_c=0.1565, halve=17, mouth=0.25, cutup=0.32, flue=0.015, pressure=870.0, end="open",
                        offset=1.0),
    # Quint 5 1/3: the twelfth's scale (smaller than the unison's, OSR p.268)
    "quint513": dict(d_c=0.0612 * 2 ** (19 / 17.0), halve=17, mouth=0.25, cutup=0.32, flue=0.015,
                     pressure=870.0, end="open", offset=1.0),
    # ---- the flutes (AOB2 p.453-457, 537-543; organ_notes 1.4, 3). A wood
    # pipe is square-ish: its d_c the circle of the same area, its mouth the
    # whole of one (the narrower) side as a share of that circle's round.
    # Gedeckt, metal: C (tenor, 8' stop) 2.55 in on root 8 (halving on the
    # 17th), mouth 1/4, cut-up 1/4-1/2 (Hindley 3/5): 1/2
    "gedakt": dict(d_c=0.0648 * 2 ** (12 / 16.0), halve=16, mouth=0.25, cutup=0.5, flue=0.015, pressure=870.0,
                   end="stopped", offset=1.0),
    # manual Bourdon 16, wood: CCC 3.76x5.10 to 5.10x7.20 in -> 4.4 x 6.2;
    # German mouths "two-thirds their width to ... exceeding": 0.7
    "bourdon16": dict(d_c=2 * math.sqrt(0.1118 * 0.1575 / math.pi) * 2 ** (-12 / 16.0), halve=16,
                      mouth=0.1118 / (2 * math.pi * math.sqrt(0.1118 * 0.1575 / math.pi)), cutup=0.7,
                      flue=0.015, pressure=870.0, end="stopped", wood=True, offset=1.0),
    # Pedal Bourdon (subbass) 16, wood: OTC spec CCC 7.26 x 9.28 in, on 2.66
    "subbass16": dict(d_c=2 * math.sqrt(0.1844 * 0.2357 / math.pi) * 2 ** (-12 / 17.0), halve=17,
                      mouth=0.1844 / (2 * math.pi * math.sqrt(0.1844 * 0.2357 / math.pi)), cutup=0.7,
                      flue=0.015, pressure=870.0, end="stopped", wood=True, offset=1.0),
    # Rohrflöte (the koppelflute's and the nazard's form, half-covered): C
    # 2.66 in on root 8, mouth 1/4, cut-up ~1/2 (arched), the chimney 1/4 the
    # body's diameter and 0.4 its length (Audsley: 1/4 D, 1/3-1/2 L)
    "rohrflute": dict(d_c=0.0676 * 2 ** (12 / 16.0), halve=16, mouth=0.25, cutup=0.5, flue=0.015,
                      pressure=870.0, end="chimney", chimney=(0.4, 0.25), offset=1.0),
    # Waldflöte as Audsley's English one, OPEN WOOD of the Melodia's scale
    # (CC 3 1/4 x 4 1/4 in, halving on the 19th), Clarabella-like cut-up 1/3
    "waldflute": dict(d_c=2 * math.sqrt(0.0826 * 0.1080 / math.pi), halve=18,
                      mouth=0.0826 / (2 * math.pi * math.sqrt(0.0826 * 0.1080 / math.pi)), cutup=0.33,
                      flue=0.015, pressure=870.0, end="open", wood=True, offset=1.0),
    # ---- the strings (AOB2 p.550-558; organ_notes 1.5): Viola da Gamba, OTC
    # spec, cylindrical, CC 3.51 in on 1:2.519 (halving on the 19th), mouth
    # 1/4 of the circumference, cut-up 1/4, and a HARMONIC BRIDGE -- which
    # "curbs [the pipe] back to the ground tone" from the octave a narrow scale
    # speaks: the fundamental's regime, which the harmonic balance solves
    "gamba": dict(d_c=0.0892, halve=18, mouth=0.25, cutup=0.25, flue=0.015, pressure=870.0, end="open",
                  offset=1.0, morph=True),         # (reached from the principal: morph())
    # Tierce: open metal at a flute's (the Rohrflöte's) wider scale, cut-up 1/3
    "tierce": dict(d_c=0.0676 * 2 ** (12 / 16.0), halve=16, mouth=0.25, cutup=0.33, flue=0.015,
                   pressure=870.0, end="open", offset=1.0),
}


def geometry(stop, f0):
    """The pipe's dimensions at sounding pitch f0: radius, mouth width B,
    cut-up W, flue height h -- from the stop's scale halving every `halve`
    semitones from its C."""
    s = STOPS[stop] if isinstance(stop, str) else stop
    semis = 12 * math.log2(f0 / 65.406)
    d = s["d_c"] * 0.5 ** (semis / s["halve"])
    a = d / 2
    B = s["mouth"] * math.pi * d
    W = s["cutup"] * B
    h = s["flue"] * d
    # THE VOICER'S CUT-UP: the scale halves slower than the wavelength, so a
    # fixed ratio leaves the treble jet too slow for its period and the pipe
    # overblows; voicers cut the treble lower, keeping the jet's transit at
    # the same share of the period it has at VOICE_REF_HZ (never above the
    # stop's own ratio)
    if s.get("voice_lower", True):
        ref = geometry(dict(s, voice_lower=False), VOICE_REF_HZ)
        if ref["W"] * VOICE_REF_HZ / f0 < W:
            W = ref["W"] * VOICE_REF_HZ / f0
            # ...and THE FLUE WITH IT: voicers keep the cut-up in proportion to
            # the windway (the jet's growth goes as W/h; the cut-up alone
            # lowered, the treble jet loses its gain and the pipe falls silent)
            h = W * ref["h"] / ref["W"]
        # ...and wherever the stop's own ratio would make the jet's transit
        # over the cut-up longer than JET_PHASE_MAX of the period (a high-cut
        # Bourdon's bass, where the fundamental can no longer start), the
        # voicer cuts it to that, the flue with it
        wcap = JET_PHASE_MAX * JET_CP * math.sqrt(2 * s["pressure"] / RHO) / (2 * math.pi * f0)
        if W > wcap:
            h = h * wcap / W
            W = wcap
    return dict(a=a, B=B, W=W, h=h, p=s["pressure"], end=s["end"], s=s)


def _sections(g, L):
    end = g["end"]
    wood = bool(g["s"].get("wood", False))
    if end == "conical":
        return [PI.cone(L, g["a"], g["a"] * g["s"].get("taper", 0.5), wood=wood)], ("open",)
    if end == "stopped":
        return [PI.cylinder(L, g["a"], wood=wood)], ("closed",)
    if end == "chimney":
        cl, cr = g["s"].get("chimney", (0.3, 0.3))
        return [PI.cylinder(L, g["a"], wood=wood)], ("chimney", cl * L, cr * g["a"])
    return [PI.cylinder(L, g["a"], wood=wood)], ("open",)


def loop_admittance(g, L, f):
    """Y(f) the jet drives: the pipe from its mouth plus the mouth's own
    radiation and lip inertance, in series."""
    secs, end = _sections(g, L)
    w = 2 * math.pi * f
    Sm = g["B"] * g["W"]
    am = math.sqrt(Sm / math.pi)
    Zm = PI.radiation(w, am) + 1j * w * RHO * LIP_THICK_M / Sm
    return 1.0 / (PI.input_impedance(f, secs, end) + Zm), secs, end


def end_ratio(secs, end, f):
    """Each frequency's far-end flow over its mouth flow (0 for a stopper)."""
    if end[0] == "closed":
        return np.zeros(len(f), complex)
    w = 2 * math.pi * f
    if end[0] == "chimney":
        a_end = end[2]
        Zt = PI.input_impedance(f, [PI.cylinder(end[1], end[2])], ("open",))
    else:
        a_end = PI._flat(secs)[-1][2]
        Zt = PI.radiation(w, a_end)
    p, U = Zt.astype(complex), np.ones(len(f), complex)
    for _, Ls, a, loss in reversed(PI._flat(secs)):
        zc, gm = PI.keefe(w, a, loss)
        ch, sh = np.cosh(gm * Ls), np.sinh(gm * Ls)
        p, U = ch * p + zc * sh * U, sh / zc * p + ch * U
    ratio = 1.0 / U
    if end[0] == "chimney":                      # the chimney's own far end
        zc, gm = PI.keefe(w, end[2])
        Zr = PI.radiation(w, end[2])
        ratio = ratio / (np.cosh(gm * end[1]) + np.sinh(gm * end[1]) * Zr / zc)
    return ratio


def tuned_length(g, f0):
    """The body length whose first loop mode sits at f0."""
    L = C / (2 * f0) * (0.5 if g["end"] in ("stopped", "chimney") else 1.0)
    for _ in range(6):
        f = np.linspace(0.7 * f0, 1.3 * f0, 3000)
        md = PI.modes(f, loop_admittance(g, L, f)[0], nmax=1)
        if not md:
            break
        L *= md[0][0] / f0
    return L


def pipe_modes(g, f0):
    """The pipe's modes up to MAX_HZ: (Hz, Q, residue weight, end ratio)."""
    L = tuned_length(g, f0)
    top = min(MAX_HZ, 0.45 * SR)
    f = np.linspace(0.5 * f0, top, int((top - 0.5 * f0) / (f0 / 400.0)))
    Y, secs, end = loop_admittance(g, L, f)
    md = PI.modes(f, Y, nmax=80)
    # real resonances only: plane waves stop at the first cross-mode (ka 1.84),
    # and a peak with Q under MIN_Q is the radiation's slope, not a mode
    md = [m for m in md if m[1] >= MIN_Q and 2 * math.pi * m[0] / C * g["a"] < 1.84]
    er = end_ratio(secs, end, np.array([m[0] for m in md]))
    # each mode a resonance Y_n(s) = A s / (s^2 + s w/Q + w^2): its peak is A Q / w
    return L, [(fm, q, pk * 2 * math.pi * fm / q, e) for (fm, q, pk), e in zip(md, er)]


def simulate(stop, f0, secs=1.5, vel=100, pressure=None, seed=1, out_sr=48000):
    """One note held from t = 0: the radiated signal at out_sr and the mouth
    flow, both float arrays."""
    g = geometry(stop, f0)
    if pressure is not None:
        g["p"] = float(pressure)
    L, md = pipe_modes(g, f0)
    T = 1.0 / SR
    wn = np.array([2 * math.pi * m[0] for m in md])
    qn = np.array([m[1] for m in md])
    An = np.array([m[2] for m in md])
    En = np.array([m[3] for m in md])
    # A s / (s^2 + s w/Q + w^2) = r / (s - s1) + conj, s1 = -w/2Q + j w sqrt(1 - 1/4Q^2)
    s1 = -wn / (2 * qn) + 1j * wn * np.sqrt(np.maximum(1 - 1 / (4 * qn ** 2), 1e-9))
    r1 = An * s1 / (s1 - np.conj(s1))
    pole = np.exp(s1 * T)
    gain = r1 * (pole - 1) / s1            # zero-order hold of the drive over a step
    z = np.zeros(len(md), complex)
    B, W, h = g["B"], g["W"], g["h"]
    Sm = B * W
    b = 0.4 * h + JET_SPREAD * W                  # the jet widens on its way to the lip
    y0 = g["s"].get("offset", 0.1) * h
    dd = 4 / math.pi * math.sqrt(2 * h * W)
    jgain = math.exp(min(JET_MU / h * W, JET_EXP_MAX))
    kdrv = RHO * dd / Sm
    kv = 0.5 * RHO / (ALPHA_VC * Sm) ** 2          # the loss as a pressure on the flow
    G = 2.0 * gain.real.sum()                       # the modes' instantaneous flow per pascal
    n = int(secs * SR)
    pal = PALLET_GENTLE_S * (PALLET_SHARP_S / PALLET_GENTLE_S) ** ((max(1, min(127, vel)) - 1) / 126.0)
    rise = pal + FOOT_RISE_S
    tt = np.arange(n) * T
    pfoot = g["p"] * np.where(tt < rise, 0.5 - 0.5 * np.cos(np.pi * np.minimum(tt / rise, 1.0)), 1.0)
    uj = np.sqrt(2 * pfoot / RHO)
    rng = np.random.default_rng(seed)
    # the jet's turbulence: white noise low-passed at the jet's own frequency (Uj / h scale)
    fc = 0.2 * math.sqrt(2 * g["p"] / RHO) / h
    al = 1 - math.exp(-2 * math.pi * min(fc, 0.4 * SR) * T)
    noise = rng.standard_normal(n)
    turb = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += al * (noise[i] - acc)
        turb[i] = acc
    turb *= TURB_REL / (np.std(turb) + 1e-12)
    vhist = np.zeros(n)
    qout = np.zeros(n)
    eout = np.zeros(n)
    qin_prev = 0.0
    q = 0.0
    for i in range(n):
        u = uj[i]
        vhist[i] = q / Sm
        if u > 0.05:
            tau = W / (JET_CP * u) * SR
            j = i - tau
            if j >= 1:
                j0 = int(j)
                fr = j - j0
                vd = vhist[j0] * (1 - fr) + vhist[j0 + 1] * fr
            else:
                vd = 0.0
            eta = h / u * jgain * vd
            sat = g["s"].get("sat", ETA_SAT)
            if sat:
                eta = sat * b * math.tanh(eta / (sat * b))
            qin = B * b * u * (1 + math.tanh((eta - y0) / b)) * (1 + turb[i])
        else:
            qin = 0.0
        djet = kdrv * (qin - qin_prev) * SR      # (the sign the loop's phase asks: loop_gain)
        qin_prev = qin
        # the vortex loss implicitly: q = qf + G dp, dp = djet - kv q|q| (one root)
        zf = pole * z
        qf = 2.0 * zf.real.sum()
        qa = qf + G * djet
        if qa != 0.0:
            c2 = G * kv
            q = math.copysign((-1.0 + math.sqrt(1.0 + 4.0 * c2 * abs(qa))) / (2.0 * c2), qa) if c2 > 0 else qa
        else:
            q = 0.0
        dp = djet - kv * q * abs(q)
        z = zf + gain * dp
        qout[i] = q
        eout[i] = 2.0 * (z * En).real.sum()
    # radiated: d/dt of the mouth's and the far end's flows, as powers (a listener off-axis)
    dm = np.diff(qout, prepend=0.0) * SR
    de = np.diff(eout, prepend=0.0) * SR
    step = SR // out_sr
    k = np.ones(step) / step
    dm = np.convolve(dm, k, "same")[::step]
    de = np.convolve(de, k, "same")[::step]
    return dm, de, dict(L=L, modes=md, g=g)


def steady(stop, f0, pressure=None, nh=32, npts=512, gain=None, guess=None):
    """THE STEADY TONE BY HARMONIC BALANCE, in the frequency domain: the
    periodic mouth flow on the FUNDAMENTAL's regime -- the one a pipe is
    voiced to speak on -- its harmonics Q_m and its frequency solved together
    so that each harmonic of the flow is what the pipe's exact admittance
    Y(m w) makes of the drive's: Q_m = Y(m w) dp_m. The jet, the lip and the
    loss are evaluated over one period (npts samples) and taken back to
    harmonics by FFT. Returns (played Hz, radiated dB re h1 per harmonic,
    level dB, the solution)."""
    from scipy.optimize import least_squares
    g = geometry(stop, f0)
    if pressure is not None:
        g["p"] = float(pressure)
    L = tuned_length(g, f0)
    secs, end = _sections(g, L)
    B, W, h = g["B"], g["W"], g["h"]
    Sm = B * W
    b = 0.4 * h + JET_SPREAD * W
    y0 = g["s"].get("offset", 0.1) * h
    uj = math.sqrt(2 * g["p"] / RHO)
    dd = 4 / math.pi * math.sqrt(2 * h * W)
    kdrv = RHO * dd / Sm
    kv = 0.5 * RHO / (ALPHA_VC * Sm) ** 2
    jg = h / uj * math.exp(min(JET_MU / h * W, JET_EXP_MAX)) if gain is None else h / uj * gain
    tau = W / (JET_CP * uj)
    m = np.arange(1, nh + 1)
    am = math.sqrt(Sm / math.pi)

    def Yof(fr):
        w = 2 * math.pi * fr
        Zm = PI.radiation(w, am) + 1j * w * RHO * LIP_THICK_M / Sm
        return 1.0 / (PI.input_impedance(fr, secs, end) + Zm)

    def unpack(x):
        Q = x[:nh] + 1j * np.concatenate([[0.0], x[nh:2 * nh - 1]])
        return Q, x[-1]

    def synth(H):           # harmonics (m = 1..nh) of a real signal -> one period
        spec = np.zeros(npts // 2 + 1, complex)
        spec[1:nh + 1] = H * npts / 2
        return np.fft.irfft(spec, npts)

    def harm(xt):
        return np.fft.rfft(xt)[1:nh + 1] * 2 / npts

    def resid(x):
        Q, fr = unpack(x)
        w = 2 * math.pi * fr
        v = Q / Sm
        eh = jg * v * np.exp(-1j * m * w * tau)
        sat = g["s"].get("sat", ETA_SAT)
        if sat:
            # the jet's AMPLITUDE saturates (it rolls up), its waveform kept:
            # its whole swing (every harmonic's, as an rms) at most ~ETA_SAT x b,
            # every harmonic scaled alike
            a1 = 2 * math.sqrt(float(np.sum(np.abs(eh) ** 2))) + 1e-30
            eh = eh * (sat * b * math.tanh(a1 / (sat * b)) / a1)
        eta = synth(eh)
        qin = B * b * uj * (1 + np.tanh((eta - y0) / b))
        vt = synth(v)
        dp = 1j * m * w * kdrv * harm(qin) - harm(kv * (vt * Sm) * np.abs(vt * Sm))
        r = Q - Yof(m * fr) * dp
        sc = 1e-4
        return np.concatenate([r.real, r.imag]) / sc

    if guess is None:
        x0 = np.zeros(2 * nh)
        x0[0] = 0.3 * uj * Sm          # a flow swing of ~0.3 Uj through the mouth
        x0[-1] = f0
    else:
        x0 = guess
    sol = least_squares(resid, x0, method="lm", xtol=1e-12, ftol=1e-12, max_nfev=4000)
    Q, fr = unpack(sol.x)
    w = 2 * math.pi * fr
    er = end_ratio(secs, end, m * fr)
    pw = (np.abs(1j * m * w * Q) ** 2) + (np.abs(1j * m * w * Q * er) ** 2)
    db = 10 * np.log10(pw / pw[0] + 1e-30)
    return fr, db, 10 * np.log10(pw.sum() + 1e-30), dict(sol=sol, Q=Q, L=L, cost=sol.cost, g=g)


def onset(stop, f0, vel=100, secs=0.6, nh=16, npts=256, seed_rel=1e-3, steady_sol=None, dt=None):
    """THE SPEECH, IN THE FREQUENCY DOMAIN: each harmonic's complex amplitude
    Q_m(t) relaxes toward what the pipe's admittance makes of the drive,
    Y(m w) dp_m(Q), at the rate the pipe answers there -- the bandwidth of
    the mode nearest m w, w_n / 2Q_n -- while the foot fills through the
    pallet (Uj and the jet's delay following it). The jet, the lip and the
    loss are the steady solver's, evaluated over one period from the
    harmonics of the moment. It starts from the jet switching on, a step of
    flow (seed_rel of the steady swing, falling as 1/m, phases at random), so
    the harmonics race: an upper one may lead (the chiff) before the
    fundamental takes the jet.
    Returns (t, radiated amplitude per harmonic [n_t, nh], played Hz)."""
    g = geometry(stop, f0)
    if steady_sol is None:
        steady_sol = steady(stop, f0, nh=nh)
    fr = steady_sol[0]
    # only the harmonics the pipe RESONATES build: past its last mode the
    # radiation answers at once and nothing there sustains itself (they take
    # the steady solution's level as the fundamental settles)
    md0 = pipe_modes(g, f0)[1]
    top = max(x[0] for x in md0) if md0 else fr
    nh = int(max(4, min(nh, math.floor(top * 1.02 / fr))))
    Qss = steady_sol[3]["Q"][:nh]
    L = steady_sol[3]["L"]
    secs_, end = _sections(g, L)
    B, W, h = g["B"], g["W"], g["h"]
    Sm = B * W
    b = 0.4 * h + JET_SPREAD * W
    y0 = g["s"].get("offset", 0.1) * h
    dd = 4 / math.pi * math.sqrt(2 * h * W)
    kdrv = RHO * dd / Sm
    kv = 0.5 * RHO / (ALPHA_VC * Sm) ** 2
    m = np.arange(1, nh + 1)
    w = 2 * math.pi * fr
    am = math.sqrt(Sm / math.pi)
    fm = m * fr
    Zm = PI.radiation(2 * math.pi * fm, am) + 1j * 2 * math.pi * fm * RHO * LIP_THICK_M / Sm
    Y = 1.0 / (PI.input_impedance(fm, secs_, end) + Zm)
    # EACH HARMONIC CARRIES ITS NEAREST MODE as a complex pole s1 (residue r1)
    # in a frame rotating at m w -- the mode's detuning from the harmonic kept
    # (a stopped pipe's 3rd and 5th modes are not at 3x and 5x) -- and the rest
    # of the admittance (every other mode, the conjugate pole, the
    # radiation's) answering at once: steady, Q_m = Y(m w) dp_m exactly, the
    # harmonic balance's state
    md = md0
    mf = np.array([x[0] for x in md])
    nn = [int(np.argmin(abs(mf - f))) for f in fm]
    wn = np.array([2 * math.pi * md[k][0] for k in nn])
    qn = np.array([md[k][1] for k in nn])
    An = np.array([md[k][2] for k in nn])
    s1 = -wn / (2 * qn) + 1j * wn * np.sqrt(np.maximum(1 - 1 / (4 * qn ** 2), 1e-9))
    r1 = An * s1 / (s1 - np.conj(s1))
    Yrest = Y - r1 / (1j * 2 * math.pi * fm - s1)
    arot = s1 - 1j * 2 * math.pi * fm                 # the pole in the harmonic's frame
    lam = wn / (2 * qn)
    er = end_ratio(secs_, end, fm)
    pal = PALLET_GENTLE_S * (PALLET_SHARP_S / PALLET_GENTLE_S) ** ((max(1, min(127, vel)) - 1) / 126.0)
    rise = pal + FOOT_RISE_S
    rng = np.random.default_rng(1)
    # the start: the jet switching on is a STEP of flow, whose spectrum falls as
    # 1/m -- the low harmonics get the head start the turbulence alone would not
    Q = seed_rel * np.abs(Qss).max() / m * np.exp(2j * np.pi * rng.random(nh))
    # the drive is explicit: a step must not move a harmonic by more than its loop
    # gain (x10-20) can undo -- lam dt well under 1/G
    dt = dt or min(0.1 / lam.max(), 2e-4)
    n = int(secs / dt)
    tt = np.arange(n) * dt
    out = np.zeros((n, nh))

    def synth(H):
        spec = np.zeros(npts // 2 + 1, complex)
        spec[1:nh + 1] = H * npts / 2
        return np.fft.irfft(spec, npts)

    def harm(xt):
        return np.fft.rfft(xt)[1:nh + 1] * 2 / npts

    def drive(Q, t):
        p = g["p"] * (0.5 - 0.5 * math.cos(math.pi * min(t / rise, 1.0)))
        if p <= 1.0:
            return np.zeros(nh, complex)
        uj = math.sqrt(2 * p / RHO)
        tau = W / (JET_CP * uj)
        jg = h / uj * math.exp(min(JET_MU / h * W, JET_EXP_MAX))
        eh = jg * (Q / Sm) * np.exp(-1j * m * w * tau)
        sat = g["s"].get("sat", ETA_SAT)
        if sat:
            a1 = 2 * math.sqrt(float(np.sum(np.abs(eh) ** 2))) + 1e-30
            eh = eh * (sat * b * math.tanh(a1 / (sat * b)) / a1)
        qin = B * b * uj * (1 + np.tanh((synth(eh) - y0) / b))
        return 1j * m * w * kdrv * harm(qin)

    Z = Q.copy()            # the resonant parts (the seed in them)
    for i in range(n):
        t = tt[i]
        # the vortex loss IMPLICITLY, as the resistance it presents to the flow's
        # swing (its describing function, 8/3pi kv |q|max) -- stiff where the
        # mouth is small; the jet's drive explicit
        qmax = np.abs(synth(Q)).max()
        rv = 8.0 / (3.0 * math.pi) * kv * qmax
        dj = drive(Q, t)
        den = 1.0 + Yrest * rv
        a = arot - r1 * rv / den
        fz = r1 * dj / den
        ea = np.exp(a * dt)
        Z = Z * ea + fz * (ea - 1.0) / a
        Q = (Z + Yrest * dj) / den
        out[i] = np.abs(1j * m * w * Q) * np.sqrt(1 + np.abs(er) ** 2)
    return tt, out, fr


def mode_times(stop, f0, harmonics=(1, 2, 3, 4, 5), tol=0.06):
    """Each harmonic's own build time from the pipe alone, in the frequency
    domain: the time constant 2Q/w of the mode it falls on (a stopped pipe's
    even harmonics fall on none, within tol, and are left out). The first
    is the fundamental's Q."""
    g = geometry(stop, f0)
    L, md = pipe_modes(g, f0)
    out = {}
    for m in harmonics:
        k = min(md, key=lambda x: abs(x[0] - m * f0)) if md else None
        if k and abs(k[0] / (m * f0) - 1) < tol:
            # the Q on a fine grid about the peak (the survey's is coarse)
            bw = k[0] / max(k[1], 1.0)
            f = np.linspace(k[0] - 4 * bw, k[0] + 4 * bw, 2001)
            fine = PI.modes(f, loop_admittance(g, L, f)[0], nmax=3)
            q = min(fine, key=lambda x: abs(x[0] - k[0]))[1] if fine else k[1]
            out[m] = (q, 2 * q / (2 * math.pi * k[0]))
    return out


def speech_fit(tt, env, f0, nfit=4):
    """The renderer's speech from the envelopes: each harmonic's 10-90% rise
    (on its settled level), the fundamental's as cycles of a smoothstep ramp
    (10-90% = 0.608 of it), the upper ones' as m^-exp of it."""
    rises = []
    for k in range(env.shape[1]):
        e = env[:, k]
        top = np.median(e[-len(e) // 5:])
        if top <= 0:
            rises.append(float("nan"))
            continue
        i10 = np.argmax(e >= 0.1 * top)
        i90 = np.argmax(e >= 0.9 * top)
        rises.append(tt[i90] - tt[i10])
    rises = np.array(rises)
    full1 = rises[0] / 0.608
    ok = np.isfinite(rises[:nfit]) & (rises[:nfit] > 0)
    mm = np.arange(1, nfit + 1)[ok]
    ex = -np.polyfit(np.log(mm), np.log(rises[:nfit][ok] / rises[0]), 1)[0] if ok.sum() > 2 else 0.0
    peak = env.max(0) / (np.median(env[-len(env) // 5:], 0) + 1e-30)
    return dict(rises=rises, cycles=full1 * f0, exp=ex, overshoot_db=20 * np.log10(peak))


def morph(stop_to, f0, stop_from="principal", steps=12):
    """CONTINUATION IN THE CONSTRUCTION: a stop that will not solve from a
    cold start (a narrow string pulled to its octave) is reached from the
    principal's solution at f0, its dimensions moved to the stop's a step at a
    time, each solve started from the last. Returns the solution vector."""
    a, b = STOPS[stop_from], STOPS[stop_to]
    x = None
    for k in range(steps + 1):
        t = k / steps
        mid = dict(b)
        for key in ("d_c", "mouth", "cutup", "flue", "pressure", "offset", "halve"):
            if key in a and key in b:
                mid[key] = a[key] * (b[key] / a[key]) ** t if key == "d_c" else a[key] + (b[key] - a[key]) * t
        r = steady(mid, f0, guess=x)
        x = r[3]["sol"].x
    return x


def sweep(stop, f_lo, f_hi, f_start=233.1, step=2 ** (1 / 12.0), guess0=None, **kw):
    """steady() over a compass by CONTINUATION: solved first at f_start (where
    a cold start converges), then a semitone at a time outward, each solve
    started from its neighbour's harmonics (scaled by the mouth's area) --
    the regime followed, not re-found. Returns {f0: steady()'s tuple}."""
    out = {}

    def run(direction):
        f, guess, prev = f_start, (guess0.copy() if guess0 is not None else None), f_start
        while (f >= f_lo * 0.999) if direction < 0 else (f <= f_hi * 1.001):
            if guess is not None:
                g0, g1 = geometry(stop, prev), geometry(stop, f)
                sc = (g1["B"] * g1["W"]) / (g0["B"] * g0["W"])
                guess = guess.copy()
                guess[:-1] *= sc
                guess[-1] *= f / prev
            r = steady(stop, f, guess=guess, **kw)
            if not sounding(r):
                break                       # the jet model's edge: the pipe falls silent here
            out[round(f, 3)] = r
            guess, prev = r[3]["sol"].x, f
            f = f * (step if direction > 0 else 1 / step)

    run(-1)
    run(+1)
    return out


def sounding(r):
    """A steady solution that oscillates (not the silent one the solver can
    fall to): its fundamental's flow well above zero."""
    return abs(r[3]["Q"][0]) > 1e-9


def at(table, f0):
    """The sweep's solution nearest f0."""
    k = min(table, key=lambda x: abs(math.log(x / f0)))
    return table[k]


PRESSURES = (0.75, 0.875, 1.0, 1.125, 1.25)     # x the voiced pressure: the chest's sag and tremulant span


def pressure_response(stop, f0, table=None):
    """HOW THE PIPE ANSWERS ITS WIND (the harmonium's pressure tables, for the
    pipe organ): the steady tone solved at PRESSURES x the voiced pressure,
    each from the voiced solution (continuation), and fitted as powers about
    the voiced point -- pitch ~ p^a, radiated amplitude ~ p^b -- the forms the
    chest's rows already take (wind.pitch_level). And the pipe's DRAW: the
    windway's flow, flue height x mouth width x the jet's speed (the flow a
    flue spends whether it speaks or not), m^3/s at the voiced pressure.
    Returns dict(a, b, draw, points)."""
    g = geometry(stop, f0)
    p0 = g["p"]
    base = at(table, f0) if table else steady(stop, f0)
    pts = []
    for k in PRESSURES:
        if k == 1.0:
            r = base
        else:
            x = base[3]["sol"].x.copy()
            x[:-1] *= k ** 0.5                       # the flow scales as the jet's speed
            r = steady(stop, f0, pressure=p0 * k, guess=x)
        if sounding(r) and r[3]["cost"] < 1e-6:
            pts.append((k, r[0], r[2]))                 # (x pressure, played Hz, level dB of power)
    ks = np.log([q[0] for q in pts])
    a = float(np.polyfit(ks, np.log([q[1] for q in pts]), 1)[0]) if len(pts) > 2 else 0.0
    # amplitude ~ power^1/2: ln A = level dB x ln10 / 20
    b = float(np.polyfit(ks, [q[2] * math.log(10) / 20 for q in pts], 1)[0]) if len(pts) > 2 else 1.0
    draw = g["B"] * g["h"] * math.sqrt(2 * p0 / RHO)
    return dict(a=a, b=b, draw=draw, points=pts)


def ladder(dm, de, f0, sr=48000, nh=32):
    """Power at each harmonic of the steady second half, mouth and end
    summed as powers, dB re h1; and the played pitch (from the mouth flow)."""
    x = dm[len(dm) // 2:]
    y = de[len(de) // 2:]
    win = np.hanning(len(x))
    X = np.abs(np.fft.rfft(x * win)) ** 2 + np.abs(np.fft.rfft(y * win)) ** 2
    fr = np.fft.rfftfreq(len(x), 1 / sr)
    band = (fr > 0.8 * f0) & (fr < 1.2 * f0)
    fp = fr[band][np.argmax(X[band])]
    out = []
    for m in range(1, nh + 1):
        sel = (fr > (m - 0.4) * fp) & (fr < (m + 0.4) * fp)
        out.append(X[sel].max() if sel.any() and (m * fp) < 0.45 * sr else 0.0)
    out = np.array(out)
    return fp, 10 * np.log10(out / out[0] + 1e-30), 10 * np.log10(out.sum() + 1e-30)


def speech(dm, de, f0, sr=48000, nh=8):
    """Each harmonic's 10-90% rise (s), from short-time power at its frequency."""
    x = np.sqrt(dm ** 2 + de ** 2) * np.sign(dm)
    hop = int(sr * 0.002)
    nwin = int(sr * max(4.0 / f0, 0.01))
    t = np.arange(0, len(dm) - nwin, hop)
    out = []
    for m in range(1, nh + 1):
        ph = np.exp(-2j * np.pi * m * f0 * np.arange(nwin) / sr) * np.hanning(nwin)
        env = np.array([abs(np.dot(dm[s:s + nwin], ph)) ** 2 + abs(np.dot(de[s:s + nwin], ph)) ** 2 for s in t])
        env = np.sqrt(env)
        top = np.median(env[len(env) // 2:])
        if top <= 0:
            out.append(float('nan'))
            continue
        a10 = np.argmax(env >= 0.1 * top)
        a90 = np.argmax(env >= 0.9 * top)
        out.append((a90 - a10) * hop / sr)
    return out


def survey(stop="principal", keys=(36, 48, 60, 72, 84)):
    for k in keys:
        f0 = 440.0 * 2 ** ((k - 69) / 12)
        dm, de, info = simulate(stop, f0, secs=1.2)
        fp, lad, lvl = ladder(dm, de, f0)
        sp = speech(dm, de, fp)
        g = info["g"]
        print("  key %d (%.1f Hz): L %.3f m, d %.1f mm, %d modes; plays %.1f Hz (%+.0f c), level %.1f dB"
              % (k, f0, info["L"], 2e3 * g["a"], len(info["modes"]), fp, 1200 * math.log2(fp / f0), lvl))
        print("      h2-h8 %s dB" % " ".join("%.0f" % v for v in lad[1:8]))
        print("      rise h1-h4 %s ms (%.0f cycles)" % (" ".join("%.0f" % (1e3 * s) for s in sp[:4]), sp[0] * fp / 0.608))


def main(argv):
    if "--survey" in argv:
        rest = [a for a in argv[1:] if not a.startswith("--")]
        survey(*(rest[:1] or ["principal"]))
        return 0
    if "--wav" in argv:
        from scipy.io import wavfile
        rest = [a for a in argv[1:] if not a.startswith("--")]
        out, stop, key = rest[0], (rest[1:2] or ["principal"])[0], int((rest[2:3] or ["60"])[0])
        f0 = 440.0 * 2 ** ((key - 69) / 12)
        dm, de, _ = simulate(stop, f0, secs=2.0)
        y = dm + de
        y = y / (np.abs(y).max() + 1e-12) * 0.8
        wavfile.write(out, 48000, (y * 32767).astype(np.int16))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
