#!/usr/bin/env python3
"""THE HARMONIUM'S FREE REED, simulated (Ben, 2026-11-23: L10, the Debain
harmonium from physics; step 1 of the plan: the reed from geometry).

THE REED (Mustel, L'Orgue-Expressif ou Harmonium, Tome I, Paris 1903, pp.
129-146; public domain): a tongue of hard-hammered brass ("laiton ecroui")
riveted at its heel over the slot of a cast-brass frame, swinging right
through the slot both ways "sans les froler jamais". Its length runs from
12-15 cm in the lowest bass to 8-9 mm at the top, its width and thickness in
proportion; its pitch is its length and its thickness profile; its VOICING is
how high its tip rests above the slot (higher: slower to speak, rounder). A
CURVED reed ("anche courbee": Cor anglais/Flute, Bourdon/Clarinette) has its
tip bent up, so it cuts the air off gradually; the EUPHONIC reed rounds the
slot's edges. The reed sits at the inlet of its CELL, a narrow closed channel
whose outlet the key's pallet opens: the cell acts back on the tongue.

THE MODEL (Millot & Baumann, "A proposal for a minimal model of free reeds",
Acta Acustica u. Acustica 93, 2007; arXiv 2401.01606): the tongue as its
first bending mode (a damped oscillator at its tip, Q), driven by the
pressure difference across it; the flow through the reed = the tongue's
pumped flow + a free jet through the USEFUL SECTION, the whole escape area
under the bending tongue -- its front, both sides integrated along it, the
clearance gaps -- with the tongue's and the plate's thickness (their eq. 9);
Bernoulli across the reed; an upstream passage whose air inertance lets a
blown-closed reed oscillate (their sec. 3: for a (-,+) reed the instability
needs the upstream reactance positive). Here the upstream is the wind-chest
at its pressure (the wind system's), the passage the sommier's hole, and
DOWNSTREAM is Mustel's cell -- a tube closed at the reed plate's side and
opening at the pallet into the air -- a digital waveguide with an open-end
reflection. The sound is the flow leaving the cell, differentiated.

THE CHECKS (Cottingham et al., ASA meetings 1995-97 on harmonium-type reeds
from an American reed organ; Physics Today 64(3) 2011): the sounding pitch a
little under the tongue's own; falling with pressure, with a small rise at
very low pressure; the reed cell lowering the pitch and lifting the upper
harmonics; the tongue's motion nearly sinusoidal.

    python3 examples/freereed_sim.py --survey          pitch, level, brightness against pressure, across the compass
    python3 examples/freereed_sim.py --cell            the cell's effect (Cottingham: lower, brighter)
    python3 examples/freereed_sim.py --phrase OUT.wav  a phrase at pp, mf, ff (the raw reed, for the ear)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RHO_AIR = 1.2
C_AIR = 343.0
# THE TONGUE'S METAL: hard-hammered brass
BRASS_E = 1.05e11            # Pa
BRASS_RHO = 8500.0           # kg/m3
# THE COMPASS (Mustel p. 136-138): the lowest tongue 12-15 cm (the 16' C,
# 32.7 Hz), the highest 8-9 mm (the 4' top C, 4186 Hz); between them the
# length follows a power of the pitch
LEN_LOW_M, F_LOW = 0.135, 32.70
LEN_HIGH_M, F_HIGH = 0.0085, 4186.0
WIDTH_RATIO = 0.16           # width / length ("in proportion"; the accordion reed of Millot's Table 2 is 0.16)
WIDTH_MIN_M = 0.0021
# THE FRAME AND THE VOICING (Millot's Table 2, a harmonica reed, scaled by
# the tongue's length where a length is meant)
PLATE_M = 0.0009             # the frame's thickness (es)
CLEARANCE_M = 50e-6          # the gap all round the tongue in the slot (hmin)
REST_RATIO = 0.019           # the tip's rest GAP, its downstream face above the slot, / length (0.3 mm at Puranik & Scavone's 16 mm)
CURL_M = 0.0                 # the tip's extra upward bend at rest (the curved reed), m at the tip
EDGE_ROUND_M = 0.0           # the slot's edge radius (the euphonic reed), m
# THE TONGUE'S DAMPING: Puranik & Scavone's measured B5 reed, its beam damping
# R = 0.065 (ρA y_tt + R y_t): a decay of R/2ρA = 4.8 /s, Q = ω0/(R/ρA) = ~650
# (Millot's harmonica reed had 95)
Q_REED = 300.0               # (Nussbaumer & Agarwal, ICA 2016: measured reed Q 200-400)
# ST HILAIRE'S EXCITATION (St Hilaire, Wilson & Beavers, "Aerodynamic
# excitation of the harmonium reed", J. Fluid Mech. 49, 1971: the unsteady
# potential flow round the tongue in its slot presses on it with about
# rho U0 a' -- the jet's velocity times the tongue's): a drive in step with the
# tongue's velocity, local to the reed, needing no acoustic coupling (Ricot et
# al. found the same in the accordion reed); Millot's model has no such term.
# Its coefficient, ~1 by the abstract's estimate
ST_HILAIRE = 1.5            # (calibrated: the measured B5 reed starts at 200 Pa, as measured)
# ...AND ONLY ON THE WIND'S SIDE: the drive is the jet streaming past the
# tongue's face as it closes on the slot; swung through to the far side, the
# jet meets it from behind and the same flow damps it. SIDED: the drive's sign
# follows where the tongue's tip is -- +1 its downstream face above the slot,
# -1 its upstream face past the slot's far face, linear between (inside the
# plate). (A reading of St Hilaire's mechanism, not his formula: the limit
# his finite-amplitude work (JFM 67, 1975) derived is not open. Nussbaumer &
# Agarwal, ICA 2016: as the flow rises the tongue sits further in and spends
# more of each cycle inside the slot; Tarnopolsky et al.: at the limit, half
# of each cycle in the plate.)
ST_HILAIRE_SIDED = True
# THE VORTEX'S DAMPING (Tarnopolsky, Fletcher & Lai, JASA 108(1) 2000, eq. 6):
# a vortex sheds downstream on each closing, a damping proportional to the
# momentum flux the tongue's motion turns -- k = beta rho v (W + 0.8 L) x0 / m,
# m the tongue's whole mass, x0 its rest opening; beta ~1 as theirs
AERO_BETA = 1.0
# THE REED'S FEED HOLE (each reed sits over its own hole in the sommier, fed
# from the chest): its area / the slot's; None = the chest's inlet alone
FEED_HOLE_RATIO = 0.3        # (0.3: the swing halved, the reed still speaking at 300 Pa; 0.1 silenced it)
VENA = 0.6                   # the jet's contraction
# THE PASSAGE UPSTREAM (the sommier's hole) and THE CELL (Mustel's channel)
# (Puranik & Scavone, Forum Acusticum 2023, "Clamped bar model for free
# reeds": a measured harmonium reed, B5 16 x 2 x 0.4 mm, simulated with a
# 50 mm near-field region of 64 mm^2 upstream -- twice its slot -- the tip
# 0.1 mm from its support; it speaks from ~200 Pa, real harmoniums 0.2-1.5 kPa)
PASSAGE_LEN_M = 0.050
PASSAGE_AREA_RATIO = 2.0     # its area / the slot's (L x W)
# THE CHEST (Mustel's "caisse a vent": one small rigid chest between the
# reservoir and the reeds): its air's compliance, with the passage, is what
# lets a blown-closed reed take energy from the flow (Millot & Baumann sec. 3:
# a chest held at a fixed pressure -- an infinite volume -- leaves it stable).
# Fed from the regulated pressure through its inlet. Puranik & Scavone's
# chamber: 1.3 litres
CHEST_M3 = 5e-6              # the reed's WELL behind it, fed through its hole from the chest
CHEST_INLET_M2 = 1.0e-4
FEED_FLOW_M3S = None         # (a check: the chest fed by a constant flow instead, Millot's minimal configuration)
REST_SIDE = 1                # +1 the tongue rests upstream of the plate, pushed into it (blown-closed);
                             # -1 through it, downstream (Millot's other reed)
CELL_LEN_RATIO = 1.2         # the cell's length / the tongue's (each reed's channel about its own length;
                             # Cottingham: the cell's length and shape matter to the spectrum more than the reed's)
CELL_AREA_RATIO = 1.5        # the cell's cross-section / the slot's
JET_LEN_M = 0.0013           # the jet's inertial length: the slot's depth and the tongue's (Millot's es + er)
# THE PALLET (Mustel: at the cell's OUTLET): before the key, the well and the
# cell stand at the chest's pressure, no flow; the key opens the outlet at
# once and the drop runs back down the cell to the reed -- a step across the
# tongue (Cottingham & Wolff's "initial displacement of the equilibrium
# position"), not a ramp. True: that; False: the supply ramped (attack_s)
PALLET_STEP = True
# ...opening over the key's travel, not in one sample: an outlet opened
# instantly made a spike 31 dB over the note (Ben: "a click in between each
# note"). The outlet's reflection goes from closed (+1) to open over this
PALLET_OPEN_S = 0.008
# ...AND THE KEY'S TOUCH IS ITS SPEED (Ben, 2026-11-23): a sharp press opens
# the pallet faster, a bigger kick to the tongue, speech sooner -- the one way
# a harmonium's key, which sets no loudness, answers touch (Mustel's
# Percussion stop is the extreme of it). simulate(vel=): its opening time from
# GENTLE (vel 0) to SHARP (vel 1), log-interpolated
# (a real pallet has mass, spring and travel: even a quick finger opens it
# over milliseconds -- at 0.5 ms the cell's air vented as a click 3 dB under
# the note, Ben: "adjust it away"; at 4 ms the puff is a soft thump under
# ~250 Hz, 19-31 dB under the note)
PALLET_OPEN_GENTLE_S = 0.015
PALLET_OPEN_SHARP_S = 0.004
# THE JET'S TURBULENCE: a real jet is never smooth -- broadband pressure
# fluctuations on the tongue, a share of the pressure drop across it (rms;
# low-passed at 10 kHz), seeding the growth the way a smooth simulation can't
TURB_REL = 0.03              # (no measured level found: 3% gives Cottingham & Wolff's few irregular first cycles)
OPEN_END_LOSS = 0.98         # the outlet's reflection magnitude (radiation takes the rest)
SR = 48000 * 8
LAST_P1 = 0.0


def tongue(f0):
    """(length, width, thickness) of the reed sounding f0: its length by the
    compass's power law, its width in proportion, its thickness what a
    uniform cantilever of that length needs for f0 (f1 = 1.875^2/(2 pi L^2)
    sqrt(E t^2 / 12 rho)) -- a profile's scraping folded into an equivalent
    uniform tongue."""
    k = np.log(LEN_HIGH_M / LEN_LOW_M) / np.log(F_HIGH / F_LOW)
    L = LEN_LOW_M * (f0 / F_LOW) ** k
    W = max(WIDTH_MIN_M, WIDTH_RATIO * L)
    t = f0 * 2.0 * np.pi * L * L / (1.875 ** 2 * np.sqrt(BRASS_E / (12.0 * BRASS_RHO)))
    return L, W, t


# the first cantilever mode, tip-normalised, and its integrals
_S = np.linspace(0.0, 1.0, 201)
_B = 1.8751040687
_SG = (np.cosh(_B) + np.cos(_B)) / (np.sinh(_B) + np.sin(_B))
_PSI = (np.cosh(_B * _S) - np.cos(_B * _S)) - _SG * (np.sinh(_B * _S) - np.sin(_B * _S))
_PSI /= _PSI[-1]
_I1 = np.trapz(_PSI, _S)          # 0.3915: the tongue's swept area per unit tip motion
_I2 = np.trapz(_PSI ** 2, _S)     # 0.25: its modal mass share
# ...AND ITS HIGHER BENDING MODES (the clamped-free beam's: Puranik & Scavone's
# Euler-Bernoulli bar, in modal form): MODES of them, each tip-normalised, its
# frequency (beta_k / beta_1)^2 the first's
MODES = 1
_BETAS = (1.8751040687, 4.6940911330, 7.8547574382, 10.9955407349)


def _mode(b):
    sg = (np.cosh(b) + np.cos(b)) / (np.sinh(b) + np.sin(b))
    y = (np.cosh(b * _S) - np.cos(b * _S)) - sg * (np.sinh(b * _S) - np.sin(b * _S))
    return y / y[-1]


_PSIK = np.array([_mode(b) for b in _BETAS])
_I1K = np.trapz(_PSIK, _S, axis=1)
_I2K = np.trapz(_PSIK ** 2, _S, axis=1)
_RATIO2 = (np.array(_BETAS) / _BETAS[0]) ** 2


USEFUL = "millot"             # the escape area: Millot & Baumann's whole area ("millot"), or the tip's alone ("tip",
                             # Puranik & Scavone's W sqrt((y + dy)^2 + hmin^2), its sides in a factor)
TIP_SIDES_FACTOR = 1.0


def useful_section(prof, L, W, t, rest_curl):
    """prof: the tongue's neutral line along it (m, at _S)"""
    if USEFUL == "tip":
        y = prof[-1] - 0.5 * t                      # the tongue's downstream face at the tip, re the slot's upstream face
        return TIP_SIDES_FACTOR * W * np.sqrt(y * y + CLEARANCE_M ** 2)
    return _useful_millot(prof, L, W, t, rest_curl)


def _useful_millot(prof, L, W, t, rest_curl):
    """The escape area under the tongue (Millot & Baumann's eq. 9, thin-plate
    reading): its tip at h (m, + = upstream of the plate's upstream face,
    the tongue's downstream face at h - t/2 at the tip), the tongue a first-
    mode profile plus the curl, the plate's slot es deep; at each point of
    the sides the local opening is how far the tongue's face is clear of the
    slot (above its upstream face, or through and past its downstream
    face), with the clearance gap always open; the front the same at the
    tip. The euphonic reed's rounded edge opens the gap gradually by the
    edge radius."""
    prof = prof + rest_curl * _S ** 3
    lo = prof - 0.5 * t                      # the tongue's downstream face along it
    hi = prof + 0.5 * t
    # clear above the slot's upstream face (0), or through its downstream face (-PLATE)
    open_ = np.where(lo > 0.0, lo, np.where(hi < -PLATE_M, -PLATE_M - hi, 0.0))
    if EDGE_ROUND_M > 0.0:
        d = np.where(lo > 0.0, 0.0, np.minimum(np.abs(lo), np.abs(hi + PLATE_M)))
        open_ = open_ + np.maximum(0.0, EDGE_ROUND_M - np.sqrt(np.maximum(0.0, 2 * EDGE_ROUND_M * d)))
    gap = np.sqrt(open_ ** 2 + CLEARANCE_M ** 2)
    sides = 2.0 * L * np.trapz(gap, _S)
    front = (W + CLEARANCE_M) * gap[-1]
    return sides + front


def simulate(f0, p0, secs=1.0, cell=True, attack_s=0.02, out_sr=48000, vel=None):
    """The reed sounding f0 at chest pressure p0 (Pa), the pallet opening
    over attack_s: (the radiated signal at out_sr, the tongue's tip motion,
    the playing frequency from its zero crossings)."""
    L, W, t = tongue(f0)
    K = MODES
    m_k = BRASS_RHO * W * t * L * _I2K[:K]
    w_k = 2.0 * np.pi * f0 * _RATIO2[:K]
    k_k = m_k * w_k ** 2
    Sr_k = W * L * _I1K[:K]                # each mode's pumped-flow and pressure-force area
    Sr = Sr_k[0]
    PS = _PSIK[:K]
    m_tot = BRASS_RHO * W * t * L
    rest_gap = REST_RATIO * L
    open_s = PALLET_OPEN_S if vel is None else \
        PALLET_OPEN_GENTLE_S * (PALLET_OPEN_SHARP_S / PALLET_OPEN_GENTLE_S) ** min(max(vel, 0.0), 1.0)
    rest = (REST_RATIO * L + 0.5 * t) if REST_SIDE > 0 else -(REST_RATIO * L + 0.5 * t + PLATE_M)
    slot = W * L
    Sp = PASSAGE_AREA_RATIO * slot
    Mp = RHO_AIR * PASSAGE_LEN_M / Sp      # the passage's inertance
    # the cell: a waveguide, delay one way
    Sc = CELL_AREA_RATIO * slot
    Zc = RHO_AIR * C_AIR / Sc
    nd = max(2, int(round(CELL_LEN_RATIO * L / C_AIR * SR))) if cell else 0
    fwd = np.zeros(nd + 1)
    bwd = np.zeros(nd + 1)
    if PALLET_STEP and cell:
        fwd[:] = bwd[:] = 0.5 * p0          # (the cell at the chest's pressure, still: half each way)
    dt = 1.0 / SR
    n = int(secs * SR)
    dec = SR // out_sr
    out = np.zeros(n // dec)
    tip = np.zeros(n // dec)
    q = np.zeros(MODES)                   # the modes' displacements (m at the tip), velocities
    rng = np.random.default_rng(1)
    tn_a = np.exp(-2.0 * np.pi * 10000.0 / SR)
    tn_b = np.sqrt(1.0 - tn_a * tn_a)        # (unit-rms one-pole noise)
    tn = 0.0
    qv = np.zeros(MODES)
    u = 0.0
    p1 = p0 if PALLET_STEP else 0.0       # the well's pressure (already full behind a closed pallet)
    vj = 0.0                              # the jet's velocity
    u_prev_flow = 0.0
    lp = 0.5 * p0 if (PALLET_STEP and cell) else 0.0   # the outlet's loss filter (at the standing wave's, behind a closed pallet)
    w0 = 2.0 * np.pi * f0
    u_out_prev = 0.0
    wi = 0
    for i in range(n):
        ramp = 1.0 if PALLET_STEP else (min(1.0, i * dt / attack_s) if attack_s > 0 else 1.0)
        P = p0 * ramp
        # pressure in the cell at the reed: what comes back plus what the flow makes
        if cell:
            back = bwd[wi]
            pc_in = 2.0 * back
        else:
            pc_in = 0.0
        # THE FLOW: u = the tongue's pumped flow + the jet, alpha Su vj, the jet
        # with its own inertia over the slot's depth (unsteady Bernoulli:
        # dp = rho vj|vj|/2 + rho l dvj/dt -- Ricot, Causse & Misdariis, JASA
        # 117(4) 2005: what drives a blown-closed reed with no acoustic coupling),
        # behind the passage's inertance (p_up = p1 - Mp du/dt) and into the
        # cell (p_dn = pc_in + Zc u)
        prof = rest * _PSI + q @ PS
        Su = useful_section(prof, L, W, t, CURL_M)
        A = -float(Sr_k @ qv)                         # (x + = upstream; moving downstream pumps air through)
        aS = VENA * Su
        Zl = Zc if cell else 0.0
        kk = Mp / dt + Zl
        rl = RHO_AIR * JET_LEN_M / dt
        # 0 = p1 - Mp (A + aS vj - u)/dt - pc_in - Zl (A + aS vj) - rho vj|vj|/2 - rl (vj - vj_prev)
        E = p1 - Mp * (A - u) / dt - pc_in - Zl * A + rl * vj
        bq = kk * aS + rl
        s_ = 1.0 if E >= 0 else -1.0
        # s rho/2 vj^2 + bq vj - E = 0, vj of sign s
        disc = bq * bq + 2.0 * RHO_AIR * abs(E)
        vj = s_ * (-bq + np.sqrt(disc)) / RHO_AIR
        u = A + aS * vj
        dp = p1 - Mp * (u - u_prev_flow) / dt - pc_in - Zl * u
        u_prev_flow = u
        # the chest: filled through its inlet from the supply, emptied by the reed
        dpi = P - p1
        inlet = CHEST_INLET_M2 if FEED_HOLE_RATIO is None else FEED_HOLE_RATIO * slot
        u_in = (FEED_FLOW_M3S * ramp if FEED_FLOW_M3S is not None else
                inlet * VENA * np.sign(dpi) * np.sqrt(2.0 * abs(dpi) / RHO_AIR))
        p1 += RHO_AIR * C_AIR * C_AIR / CHEST_M3 * (u_in - u) * dt
        # the tongue: m x'' + (m w0/Q) x' + k x = -Sr dp  (dp pushes it downstream: x -)
        p_ex = ST_HILAIRE * RHO_AIR * abs(vj) * float(qv.sum())     # (+ along the tip's motion)
        if ST_HILAIRE_SIDED:
            tipn = prof[-1]
            lo_face, hi_face = tipn - 0.5 * t, tipn + 0.5 * t
            side = 1.0 if lo_face >= 0.0 else (-1.0 if hi_face <= -PLATE_M else
                                                 1.0 - 2.0 * (-lo_face) / (PLATE_M + t))
            p_ex *= side
        c_aero = 2.0 * AERO_BETA * RHO_AIR * abs(vj) * (W + 0.8 * L) * rest_gap / m_tot
        if TURB_REL > 0.0:
            tn = tn_a * tn + tn_b * rng.standard_normal()
            dp_t = dp + TURB_REL * abs(dp) * tn
        else:
            dp_t = dp
        acc = (-Sr_k * dp_t + Sr_k * p_ex - k_k * q - m_k * w_k / Q_REED * qv) / m_k - c_aero * qv
        qv += acc * dt
        q += qv * dt
        # the cell: the flow goes in at the reed end, comes out at the pallet
        if cell:
            p_dn = pc_in + Zl * u
            f_in = p_dn - back               # the wave sent down the cell
            j = (wi + nd) % (nd + 1)
            fwd[j] = f_in
            arrive = fwd[(wi + 1) % (nd + 1)]
            lp = 0.5 * lp + 0.5 * arrive
            if PALLET_STEP and open_s > 0.0 and i * dt < open_s:
                x_ = i * dt / open_s
                r_ = 1.0 - (1.0 + OPEN_END_LOSS) * x_ * x_ * (3.0 - 2.0 * x_)   # closed +1 -> open -loss
            else:
                r_ = -OPEN_END_LOSS
            refl = r_ * lp
            bwd[(wi + nd) % (nd + 1)] = refl
            u_out = (arrive - refl) / Zc
            wi = (wi + 1) % (nd + 1)
        else:
            u_out = u
        if i % dec == 0:
            k = i // dec
            out[k] = (u_out - u_out_prev) * SR
            tip[k] = q.sum()
        u_out_prev = u_out
    global LAST_P1
    LAST_P1 = p1                          # (the chest's pressure at the end, for the checks)
    # the playing frequency over the last half
    seg = tip[len(tip) // 2:]
    zc = np.flatnonzero((seg[:-1] < np.mean(seg)) & (seg[1:] >= np.mean(seg)))
    fp = (len(zc) - 1) / ((zc[-1] - zc[0]) / out_sr) if len(zc) > 2 else 0.0
    return out, tip, fp


def ladder(y, f, sr=48000, n=16):
    s = y[len(y) // 2:]
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 17))
    fr = np.fft.rfftfreq(1 << 17, 1.0 / sr)
    h = [20 * np.log10(X[(fr > f * k * 0.97) & (fr < f * k * 1.03)].max() + 1e-20) for k in range(1, n + 1)]
    return np.array(h) - max(h)


def survey():
    for f0 in (65.41, 130.81, 261.63, 523.25, 1046.5):
        L, W, t = tongue(f0)
        print("  %7.1f Hz: tongue %.1f x %.1f mm, %.0f um" % (f0, L * 1e3, W * 1e3, t * 1e6))
        for p0 in (150.0, 400.0, 800.0, 1600.0):
            y, tip, fp = simulate(f0, p0, secs=0.6)
            amp = np.ptp(tip[len(tip) // 2:]) / 2
            lv = 10 * np.log10(np.mean(y[len(y) // 2:] ** 2) + 1e-30)
            hl = ladder(y, fp or f0, n=12) if fp else np.zeros(12)
            print("     %5.0f Pa: plays %7.2f Hz (%+5.1f c), tip +/-%.2f mm, level %6.1f dB, h1-h8 %s"
                  % (p0, fp, 1200 * np.log2(fp / f0) if fp else 0, amp * 1e3, lv,
                     " ".join("%4.0f" % v for v in hl[:8])), flush=True)


def touch_phrase(outp, p0=700.0):
    """Each note gently, then sharply: the touch as the pallet's speed."""
    from scipy.io import wavfile
    parts = []
    for f0 in (130.81, 261.63, 392.0):
        for vel in (0.15, 1.0):
            y, _, _ = simulate(f0, p0, secs=1.0, vel=vel)
            env = np.ones_like(y)
            env[-2400:] = np.linspace(1, 0, 2400)
            parts += [y * env, np.zeros(9600)]
        parts.append(np.zeros(9600))
    y = np.concatenate(parts)
    wavfile.write(outp, 48000, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))


if __name__ == "__main__":
    if "--touch" in sys.argv:
        touch_phrase(sys.argv[sys.argv.index("--touch") + 1])
    if "--survey" in sys.argv:
        survey()
    if "--cell" in sys.argv:
        for cell in (False, True):
            y, tip, fp = simulate(261.63, 800.0, secs=0.6, cell=cell)
            print("  cell %-5s plays %.2f Hz, h1-h12 %s" % (cell, fp, " ".join("%4.0f" % v for v in ladder(y, fp, n=12))))
    if "--phrase" in sys.argv:
        from scipy.io import wavfile
        outp = sys.argv[sys.argv.index("--phrase") + 1]
        parts = []
        for p0 in (300.0, 700.0, 1500.0):
            for f0 in (130.81, 196.0, 261.63, 392.0):
                y, _, _ = simulate(f0, p0, secs=0.9)
                env = np.ones_like(y)
                env[-2400:] = np.linspace(1, 0, 2400)
                parts += [y * env, np.zeros(2400)]
            parts.append(np.zeros(12000))
        y = np.concatenate(parts)
        wavfile.write(outp, 48000, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))
