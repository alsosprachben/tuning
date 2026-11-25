#!/usr/bin/env python3
"""A REED PIPE FROM ITS CONSTRUCTION: the beating tongue and its resonator --
the pipe organ's reed stops off the Piteå recordings (2026-11-24, as the flue
stops: examples/fluepipe_sim.py). Nothing fitted to a recording. Audsley gives
the resonators' forms and lengths but no tongue tables ("there are absolutely
no established rules", AOB2 p.587); what he leaves out is named, for Ben's ear.

    python3 examples/reedpipe_sim.py --survey [STOP]

THE MODEL (Fletcher & Rossing ch. 13/17; the striking reed as Fletcher's
"inward-striking" valve):

  the tongue  a brass strip clamped at the block, its free end over the
              shallot's face: one mode, resonance f_t (the tuning wire sets
              its vibrating length: TONGUE_TUNE x the note), quality Q_t, its
              mass per area rho_brass t ALPHA (t the strip's thickness, from
              the cantilever's law at its length). The wind's pressure over
              the resonator's, dp, blows it SHUT:
                  mu (y'' + w_t/Q_t y' + w_t^2 (y - y0)) = -dp + contact
              y0 its rest opening (the burnished curve), the contact a stiff
              spring where it lies on the face (y < 0)
  the slot    passes Bernoulli flow while open: U = w y+ sqrt(2|dp|/rho) sgn dp
  the pipe    the resonator's input impedance Z(f) at the shallot (examples/
              pipe_impedance.py: conical, cylindrical, short), p_res = Z U

THE STEADY TONE BY HARMONIC BALANCE (the frequency domain): the tongue's
motion and the resonator's pressure, harmonic by harmonic, and the frequency
solved together. What radiates is the resonator's open end: d/dt of its flow
(each harmonic's end/shallot flow ratio from the transmission line).

THE TONGUES (Audsley AOB2 p.594-595: Weber's scale, length and width on 1:root 8,
thickness on 1:2 -- no numbers; Roosevelt's Trombone 16: CC tongue 5 1/4 in
from the block, CCC 6 1/2 in): length 133 mm at 65.4 Hz on 1:root 8, the width
WIDTH_RATIO of it, the thickness what makes that length ring at the note.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipe_impedance as PI  # noqa: E402
import fluepipe_sim as FS  # noqa: E402

RHO, C = PI.RHO, PI.C
BRASS_E, BRASS_RHO = 1.0e11, 8500.0
ALPHA = 0.25                 # the tongue's modal mass, as a share of its own (a cantilever's tip)
TONGUE_L_CC = 0.133          # m at 65.4 Hz (Roosevelt's Trombone 16, CC: 5 1/4 in)
TONGUE_HALVE = 16            # semitones the length halves over (1:root 8)
WIDTH_RATIO = 0.18           # width over length (Audsley's free-reed tongues: 0.12-0.17; named)
TONGUE_TUNE = 1.02           # the tongue's resonance over the note (the wire; named)
Q_TONGUE = 30.0              # the tongue's quality, its leather/air losses (named, by ear)
BEAT = 2.0                   # the rest opening (the burnished curve) as a share of the tongue's
                             # deflection under the full wind: under 1 it is blown shut and stays;
                             # past ~3 it no longer beats (named, by ear)
CONTACT = 3.0                # the face's stiffness over the tongue's own: a curved tongue ROLLS
                             # onto the shallot (Audsley: English tongues "unroll" onto the face),
                             # not a hard stop -- a stiff one raised the pitch 1.7x (named, by ear)


# ---- a stop's resonator (Audsley AOB2 p.597-610; lengths re an open flue pipe)
# form     "cone" (inverted cone: top radius a_top at 65.4 Hz, halving as halve),
#          "cylinder" (radius a_cyl at 65.4 Hz), length the share of the open
#          pipe's (lam/2); harmonic = speaks its resonator's 2nd mode above
#          tenor C
STOPS = {
    # Trumpet 8: inverted cone "nearly that of an open labial pipe"; open shallot
    "trumpet": dict(form="cone", length=0.95, a_top_c=0.050, halve=17, a_in_c=0.012, pressure=870.0),
    # Trompette harmonique: the same form at ~2x length from tenor C
    "trompette": dict(form="cone", length=0.95, a_top_c=0.050, halve=17, a_in_c=0.012, pressure=870.0,
                      harmonic_from=130.8),
    # Clarion 4: Trumpet form, smaller scale
    "clarion": dict(form="cone", length=0.95, a_top_c=0.040, halve=17, a_in_c=0.010, pressure=870.0),
    # Oboe: a slender cone (its bell's flare and shading left out: named later)
    "oboe": dict(form="cone", length=0.95, a_top_c=0.030, halve=17, a_in_c=0.008, pressure=870.0,
                 curve=0.02),
    # Fagotto (basson 16): very small-scale inverted cone, Willis CC top 2 in D
    "basson": dict(form="cone", length=0.95, a_top_c=0.0254, halve=17, a_in_c=0.008, pressure=870.0,
                   curve=0.02),
    # Contrafagotto 32: as the Fagotto (its 32' lingual the Contra-Trombone's ~0.88)
    "contrabassoon": dict(form="cone", length=0.88, a_top_c=0.0254, halve=17, a_in_c=0.008, pressure=870.0,
                          curve=0.02),
    # Cromorne: small-scale cylinder at ~half length, "like the Clarinet"
    "cromorne": dict(form="cylinder", length=0.5, a_cyl_c=0.016, halve=24, pressure=870.0),
    # Vox Humana: cylinder "approximately one-fourth the length of open labial pipes"
    # (its quarter-length tube resonates near twice the note: the voicer cuts it
    # TO the second harmonic, the nasal "vowel" over a tongue that keeps the note)
    "voxhumana": dict(form="cylinder", length=0.25, a_cyl_c=0.020, halve=24, pressure=870.0, tune_to=2.0,
                      st_hilaire=1.5, tune_tongue=True, tongue_tune=0.8),   # (the tongue holds the note: tuned_tone)
}


def tongue(f0, scale=1.0, tune=None):
    """(length, width, thickness, mass per area) of the tongue at note f0;
    scale lengthens it (a tongue tuned to the same note then thicker as the
    square, heavier: the stop more the tongue's than the resonator's)."""
    semis = 12 * math.log2(f0 / 65.406)
    L = TONGUE_L_CC * 0.5 ** (semis / TONGUE_HALVE) * scale
    ft = f0 * (TONGUE_TUNE if tune is None else tune)
    # a clamped-free strip: f = (1.875^2 / 2 pi) (t / L^2) sqrt(E / 12 rho)
    t = ft * L * L / (1.875 ** 2 / (2 * math.pi) * math.sqrt(BRASS_E / (12 * BRASS_RHO)))
    return L, WIDTH_RATIO * L, t, BRASS_RHO * t * ALPHA


def _shape(s, f0, length):
    semis = 12 * math.log2(f0 / 65.406)
    k = 0.5 ** (semis / s["halve"])
    L = length * C / (2 * f0)
    if s["form"] == "cone":
        return [PI.cone(L, s["a_in_c"] * k, s["a_top_c"] * k)], ("open",)
    return [PI.cylinder(L, s["a_cyl_c"] * k)], ("open",)


def resonator(stop, f0):
    """The resonator's sections from the shallot up, and its far end. A
    voicer cuts it TO THE NOTE: its first resonance (a harmonic stop's
    second, above harmonic_from) at f0 -- Audsley's length the start; a stop
    marked untuned (the Vox Humana's short tube) keeps his length."""
    s = STOPS[stop] if isinstance(stop, str) else stop
    length = s["length"]
    nmode = 1
    target = f0 * s.get("tune_to", 1.0)        # a short resonator cut to a harmonic of the note
    if s.get("harmonic_from") and f0 >= s["harmonic_from"]:
        length *= 2.0
        nmode = 2
    if not s.get("untuned"):
        for _ in range(6):
            secs, end = _shape(s, f0, length)
            f = np.linspace(0.3 * f0, 2.6 * target * nmode, 6000)
            pk = [m[0] for m in PI.modes(f, PI.input_impedance(f, secs, end), nmax=4)]
            if len(pk) < nmode:
                break
            length *= pk[nmode - 1] / target
    return _shape(s, f0, length)


def steady(stop, f0, nh=32, npts=1024, guess=None, beat=None):
    """The beating reed's periodic state by harmonic balance: (played Hz,
    radiated dB re h1 per harmonic, level dB, info)."""
    from scipy.optimize import least_squares
    s = STOPS[stop] if isinstance(stop, str) else stop
    secs, end = resonator(s, f0)
    tune = s.get("tongue_tune", TONGUE_TUNE)
    Lt, wt, tt_, mu = tongue(f0, s.get("tongue_scale", 1.0), tune)
    wt0 = 2 * math.pi * f0 * tune
    p0 = s["pressure"]
    y0 = (beat if beat is not None else s.get("beat", BEAT)) * p0 / (mu * wt0 ** 2)
    m = np.arange(0, nh + 1)
    eps = 0.02 * y0
    kc = CONTACT * mu * wt0 ** 2

    def Zof(fr):
        return PI.input_impedance(m[1:] * fr, secs, end)

    def synth(H):                       # H[0] is the mean, H[1..] harmonic amplitudes (complex)
        spec = np.zeros(npts // 2 + 1, complex)
        spec[0] = H[0] * npts
        spec[1:nh + 1] = H[1:] * npts / 2
        return np.fft.irfft(spec, npts)

    def harm(xt):
        X = np.fft.rfft(xt)
        out = np.empty(nh + 1, complex)
        out[0] = X[0].real / npts
        out[1:] = X[1:nh + 1] * 2 / npts
        return out

    def unpack(x):
        Y = np.empty(nh + 1, complex)
        Y[0] = x[0]
        Y[1] = x[1]                      # its phase the reference
        Y[2:] = x[2:nh + 1] + 1j * x[nh + 1:2 * nh]
        P = np.zeros(nh + 1, complex)
        P[1:] = x[2 * nh:3 * nh] + 1j * x[3 * nh:4 * nh]
        return Y, P, x[-1]

    def resid(x):
        Y, P, fr = unpack(x)
        w = 2 * math.pi * fr
        y = synth(Y)
        pres = synth(P)
        dp = p0 - pres
        yp = eps * np.logaddexp(0.0, y / eps)            # the slot's opening, smooth at zero
        U = wt * yp * np.sqrt(2 * np.abs(dp) / RHO + 1e-12) * np.sign(dp)
        fc = kc * eps * np.logaddexp(0.0, -y / eps)       # the face pushing back where it lies on it
        Fh = harm(-dp + fc)
        lhs = mu * ((wt0 ** 2 - (m * w) ** 2) + 1j * m * w * wt0 / Q_TONGUE) * (Y - np.r_[y0, np.zeros(nh)])
        r1 = (lhs - Fh) / (mu * wt0 ** 2 * y0)
        Uh = harm(U)
        r2 = (P[1:] - Zof(fr) * Uh[1:]) / p0
        return np.concatenate([[r1[0].real], r1[1:].real, r1[1:].imag, r2.real, r2.imag])

    if guess is None:
        x0 = np.zeros(4 * nh + 1)
        x0[0] = 0.5 * y0
        x0[1] = 0.5 * y0
        x0[-1] = f0
    else:
        x0 = guess
    sol = least_squares(resid, x0, method="lm", xtol=1e-12, ftol=1e-12, max_nfev=6000)
    Y, P, fr = unpack(sol.x)
    w = 2 * math.pi * fr
    y = synth(Y)
    dp = p0 - synth(P)
    U = wt * eps * np.logaddexp(0.0, y / eps) * np.sqrt(2 * np.abs(dp) / RHO + 1e-12) * np.sign(dp)
    Uh = harm(U)[1:]
    er = FS.end_ratio(secs, end, m[1:] * fr)
    pw = np.abs(1j * m[1:] * w * Uh * er) ** 2
    db = 10 * np.log10(pw / pw[0] + 1e-30)
    closed = float(np.mean(y < 0))
    return fr, db, 10 * np.log10(pw.sum() + 1e-30), dict(sol=sol, cost=sol.cost, Y=Y, P=P, closed=closed,
                                                         tongue=(Lt, wt, tt_), y0=y0)


BEAT_START = 3.6             # where a cold start oscillates (the tongue swinging free of the face)


def voiced(stop, f0, steps=14, guess=None):
    """CONTINUATION IN THE VOICING: from a rest gap where the tongue swings
    free (BEAT_START x its deflection under the wind), closed step by step to
    the stop's BEAT, each solve started from the last -- the voicer curving
    the tongue down until it beats. Returns steady()'s tuple at the voicing."""
    s = STOPS[stop] if isinstance(stop, str) else stop
    target = s.get("beat", BEAT)
    r = None
    for k in range(steps + 1):
        b = BEAT_START * (target / BEAT_START) ** (k / steps)
        r = steady(s, f0, guess=guess, beat=b)
        if r[3]["cost"] > 1e-6:
            return r
        y0_ratio = 1.0
        guess = r[3]["sol"].x
    return r


def sweep(stop, f_lo, f_hi, f_start=233.1, step=2 ** (1 / 12.0)):
    """steady() over a compass by continuation, as the flue's."""
    out = {}

    def run(direction):
        f, guess, prev = f_start, None, f_start
        while (f >= f_lo * 0.999) if direction < 0 else (f <= f_hi * 1.001):
            if guess is not None:
                g = guess.copy()
                g[-1] *= f / prev
                sc = tongue(f)[0] / tongue(prev)[0]
                g[:2 * len(g) // 4] *= sc
                guess = g
            r = steady(stop, f, guess=guess)
            if abs(r[3]["Y"][1]) < 1e-3 * r[3]["y0"] or r[3]["cost"] > 1e-6:
                break
            out[round(f, 3)] = r
            guess, prev = r[3]["sol"].x, f
            f = f * (step if direction > 0 else 1 / step)

    run(-1)
    run(+1)
    return out


def survey(stop="trumpet", keys=(36, 48, 60, 72, 84)):
    for k in keys:
        f0 = 440.0 * 2 ** ((k - 69) / 12)
        fr, db, lvl, info = steady(stop, f0)
        Lt, wt, t = info["tongue"]
        print("  key %d (%.1f Hz): tongue %.0f x %.1f x %.2f mm; plays %.1f Hz (%+.0f c), cost %.0e, closed %.0f%%, "
              "level %.1f; h2-h8 %s" % (k, f0, Lt * 1e3, wt * 1e3, t * 1e3, fr, 1200 * math.log2(fr / f0),
                                        info["cost"], 100 * info["closed"], lvl,
                                        " ".join("%.0f" % d for d in db[1:8])))


if __name__ == "__main__":
    if "--survey" in sys.argv:
        rest = [a for a in sys.argv[1:] if not a.startswith("--")]
        survey(*(rest[:1] or ["trumpet"]))
    else:
        print(__doc__)


# ---- THE TIME DOMAIN, where the reed is easier there: the harmonic balance
# finds the still tongue as readily as the beating one, and a reed has no
# flue's race of modes to fear -- so the tone and the speech both come from
# the tongue stepped through time against the resonator's MODES (its
# impedance peaks from the frequency domain, each a complex one-pole stepped
# exactly), the slot's flow solved each step against the resonator's
# instantaneous answer.
SR = 96000


def res_modes(secs, end, f0, fmax=16000.0):
    """The resonator's impedance peaks: (Hz, Q, residue weight A), Z_n(s) =
    A s / (s^2 + s w/Q + w^2)."""
    f = np.linspace(0.3 * f0, min(fmax, 0.45 * SR), int((min(fmax, 0.45 * SR) - 0.3 * f0) / (f0 / 300.0)))
    Z = PI.input_impedance(f, secs, end)
    out = []
    for fm, q, pk in PI.modes(f, Z, nmax=60):
        if q >= 2.0:
            out.append((fm, q, pk * 2 * math.pi * fm / q))
    return out


def simulate(stop, f0, secs=1.0, vel=100, out_sr=48000):
    """One reed note held from t = 0. Returns (shallot flow U at out_sr, its
    radiation per frequency E(f) as a callable, info)."""
    s = STOPS[stop] if isinstance(stop, str) else stop
    rsecs, end = resonator(s, f0)
    tune = s.get("tongue_tune", TONGUE_TUNE)
    Lt, wt, tt_, mu = tongue(f0, s.get("tongue_scale", 1.0), tune)
    wt0 = 2 * math.pi * f0 * tune
    p0 = s["pressure"]
    y0 = s.get("beat", BEAT) * p0 / (mu * wt0 ** 2)
    md = res_modes(rsecs, end, f0)
    wn = np.array([2 * math.pi * x[0] for x in md])
    qn = np.array([x[1] for x in md])
    An = np.array([x[2] for x in md])
    T = 1.0 / SR
    s1 = -wn / (2 * qn) + 1j * wn * np.sqrt(np.maximum(1 - 1 / (4 * qn ** 2), 1e-9))
    r1 = An * s1 / (s1 - np.conj(s1))
    pole = np.exp(s1 * T)
    gain = r1 * (pole - 1) / s1
    G = 2.0 * gain.real.sum()
    z = np.zeros(len(md), complex)
    n = int(secs * SR)
    pal = FS.PALLET_GENTLE_S * (FS.PALLET_SHARP_S / FS.PALLET_GENTLE_S) ** ((max(1, min(127, vel)) - 1) / 126.0)
    rise = pal + FS.FOOT_RISE_S
    kc = CONTACT * mu * wt0 ** 2
    sth = s.get("st_hilaire", 0.0)
    y, v = y0, 0.0
    U = np.zeros(n)
    Y = np.zeros(n)
    for i in range(n):
        t = i * T
        pf = p0 * (0.5 - 0.5 * math.cos(math.pi * min(t / rise, 1.0)))
        zf = pole * z
        pfree = 2.0 * zf.real.sum()
        a = wt * max(y, 0.0)
        # U = a sqrt(2 |pf - p| / rho) sgn(pf - p), p = pfree + G U: solve for U
        if a > 0.0:
            lo, hi = -a * 400.0, a * 400.0
            for _ in range(40):
                u = 0.5 * (lo + hi)
                d = pf - (pfree + G * u)
                f = u - a * math.sqrt(2 * abs(d) / RHO) * math.copysign(1.0, d)
                if f > 0:
                    hi = u
                else:
                    lo = u
            u = 0.5 * (lo + hi)
        else:
            u = 0.0
        p = pfree + G * u
        z = zf + gain * u
        # the tongue (semi-implicit Euler): blown shut by the pressure across it
        acc = -wt0 / Q_TONGUE * v - wt0 ** 2 * (y - y0) - (pf - p) / mu
        if sth and y > 0.0:
            # ST HILAIRE'S DRIVE (St Hilaire, Wilson & Beavers, JFM 49 1971; the
            # harmonium's freereed_sim): the jet streaming past the moving tongue
            # presses on it in step with its velocity -- local to the reed, needing
            # no resonator: what keeps a regal's tongue on its own note
            acc += sth * RHO * math.sqrt(2.0 * abs(pf - p) / RHO) * v / mu
        if y < 0.0:
            acc += kc * (-y) / mu
        v += acc * T
        y += v * T
        U[i] = u
        Y[i] = y
    step = SR // out_sr
    k = np.ones(step) / step
    Uo = np.convolve(U, k, "same")[::step]

    def E(fr):
        return FS.end_ratio(rsecs, end, np.atleast_1d(fr))

    return Uo, E, dict(y0=y0, closed=float(np.mean(Y[n // 2:] < 0)), modes=md, tongue=(Lt, wt, tt_))


def tone(stop, f0, secs=1.0, nh=32):
    """The settled tone: played Hz, radiated dB re h1, level dB, info."""
    U, E, info = simulate(stop, f0, secs=secs)
    sr = 48000
    x = U[len(U) // 2:]
    win = np.hanning(len(x))
    X = np.fft.rfft(x * win) * 2.0 / win.sum()          # each line's amplitude, in the flow's own units
    fr_ = np.fft.rfftfreq(len(x), 1 / sr)
    band = (fr_ > 0.8 * f0) & (fr_ < 1.25 * f0)
    fp = fr_[band][np.argmax(np.abs(X[band]))]
    amps = []
    for m in range(1, nh + 1):
        sel = (fr_ > (m - 0.4) * fp) & (fr_ < (m + 0.4) * fp)
        if not sel.any() or m * fp > 0.45 * sr:
            amps.append(0.0)
            continue
        j = np.argmax(np.abs(X) * sel)
        amps.append(abs(X[j]) * abs(E(fr_[j])[0]) * 2 * math.pi * fr_[j])
    amps = np.array(amps)
    pw = amps ** 2
    return fp, 10 * np.log10(pw / pw[0] + 1e-30), 10 * np.log10(pw.sum() + 1e-30), dict(info, U=U, E=E)


def envelopes(stop, f0, secs=0.6, nh=8):
    """Each harmonic's amplitude over the attack (the shallot's flow at the
    harmonic, a short-time transform; its radiation a constant factor a
    harmonic, so the rises are the flow's): (t, env [n_t, nh], played Hz)."""
    U, E, info = simulate(stop, f0, secs=secs)
    sr = 48000
    x = U[len(U) // 2:]
    X = np.abs(np.fft.rfft((x - x.mean()) * np.hanning(len(x))))
    fr_ = np.fft.rfftfreq(len(x), 1 / sr)
    band = (fr_ > 0.8 * f0) & (fr_ < 1.25 * f0)
    fp = fr_[band][np.argmax(X[band])]
    hop = int(sr * 0.001)
    nwin = int(sr * max(4.0 / fp, 0.006))
    t = np.arange(0, len(U) - nwin, hop)
    env = np.zeros((len(t), nh))
    for m in range(1, nh + 1):
        ph = np.exp(-2j * np.pi * m * fp * np.arange(nwin) / sr) * np.hanning(nwin)
        env[:, m - 1] = [abs(np.dot(U[i:i + nwin] - U[i:i + nwin].mean(), ph)) for i in t]
    return t / sr, env, fp


def tuned_tone(stop, f0, secs=0.8, rounds=4):
    """tone() with the TONGUE TUNED TO THE NOTE, as a voicer sets a regal's
    wire: where the resonator cannot hold the pitch (the Vox Humana's short
    tube), the beating tongue -- stiffer for the part of each cycle it lies
    on the face -- sounds above its free frequency, so its wire is moved
    until the pipe speaks the note. Other stops: tone() as it is."""
    s = dict(STOPS[stop]) if isinstance(stop, str) else dict(stop)
    if not s.get("tune_tongue"):
        r = tone(s, f0, secs=secs)
        r[3]["stop"] = s
        return r
    tune = s.get("tongue_tune", TONGUE_TUNE)
    r = None
    for _ in range(rounds):
        s["tongue_tune"] = tune
        r = tone(s, f0, secs=secs)
        if r[2] < -100:
            break
        tune *= f0 / r[0]
    r[3]["stop"] = s
    return r
