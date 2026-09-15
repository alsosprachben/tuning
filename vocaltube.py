#!/usr/bin/env python3
"""The vocal tract as a TUBE, after Kelly and Lochbaum (1962).

Everything else in this renderer is modelled by its geometry -- a pipe by its
bore, a string by its stiffness -- and the voice was the exception: formants
asserted as a spectrum rather than arising from a shape. That gap is why the
consonants needed a hand-tuned band centre per place of articulation, and why
transitions had to be smoothed by interpolating formant frequencies
INDEPENDENTLY, which can pass through configurations no throat could hold.

Here the tract is what it is: a run of short cylindrical sections. At each
junction the area ratio sets a reflection coefficient

    r_k = (A_k - A_k+1) / (A_k + A_k+1)

and a wave running down the tube is partly transmitted and partly reflected at
every boundary. Formants are then not parameters; they are the resonances of
the shape, and they move TOGETHER when the shape moves, because they are
consequences of one thing.

This module does not run the scattering at sample rate -- 44 sections at
44.1 kHz is a recursive loop that belongs in C. It computes the tube's
frequency RESPONSE from its area function, which the existing STFT path in
vocaltract.py applies directly. The envelope and the way it MOVES are then
physically derived; what is given up is the exact transient of the scattering
and any source-tract coupling.
"""
import numpy as np

C_SOUND = 35000.0      # cm/s, warm moist air
TRACT_CM = 17.5        # adult male; the VOICE_BODIES ratios scale it
SECTIONS = 44          # 17.5 cm / 44 = 4.0 mm, good past 8 kHz

# Losses. A lossless tube has infinitely sharp resonances -- every formant the
# same height and no bandwidth at all -- so these are what make the response a
# spectrum rather than a comb of poles.
WALL_LOSS = 0.0034     # per cm, times sqrt(f/500): viscous + thermal at the walls
RADIATION_HZ = 4500.0  # the lips stop reflecting and start radiating


def _lip_reflectance(f):
    """The open end reflects nearly everything low and almost nothing high.

    A first-order radiation load: |r| -> 1 below RADIATION_HZ, falling above,
    always sign-inverted because an open end is a pressure node.
    """
    return -1.0 / np.sqrt(1.0 + (f / RADIATION_HZ) ** 2)


def response(areas, freqs, tract_cm=TRACT_CM, glottal_r=0.97, radiate=True,
             wall=1.0):
    """|H(f)| of a tube with these section areas, at `freqs`.

    Walks the chain reflectance from the lips back to the glottis: each section
    is a length of transmission line, each junction a change of characteristic
    impedance. Equivalent to the scattering formulation, far cheaper when only
    the response is wanted.
    """
    areas = np.asarray(areas, float)
    n = len(areas)
    L = tract_cm / n
    f = np.asarray(freqs, float)
    k = 2.0 * np.pi * f / C_SOUND
    atten = np.exp(-WALL_LOSS * wall * np.sqrt(np.maximum(f, 1.0) / 500.0) * L)
    prop = np.exp(-1j * k * L) * atten          # one section, one way
    rt = prop * prop                            # ... and back

    refl = _lip_reflectance(f).astype(complex)
    for i in range(n - 1, 0, -1):
        r = (areas[i - 1] - areas[i]) / (areas[i - 1] + areas[i])
        z = rt * refl
        refl = (r + z) / (1.0 + r * z)
    h = 1.0 / (1.0 - glottal_r * rt * refl)
    if radiate:
        # pressure radiated from the lips differentiates the volume flow
        h = h * (f / (f + RADIATION_HZ))
    return np.abs(h)


def formants(areas, tract_cm=TRACT_CM, count=3, lo=180.0, hi=5200.0, n=6000,
             bandwidths=False):
    """The tube's lowest `count` resonances in Hz (and -3 dB widths)."""
    f = np.linspace(lo, hi, n)
    H = response(areas, f, tract_cm, radiate=False)
    pk = [i for i in range(1, n - 1) if H[i] > H[i - 1] and H[i] >= H[i + 1]]
    pk = pk[:count]                       # BY FREQUENCY: the peaks of a tube
    df = f[1] - f[0]                      # are all of comparable height, so
    out = []                              # sorting by height tie-breaks at random
    for i in pk:
        # PARABOLIC INTERPOLATION, and not for accuracy's sake: without it a
        # peak can only ever sit on a grid point, so a small change in tract
        # shape moves it by exactly nothing and the fitter's Jacobian is zero.
        a, b, c = np.log(H[i - 1]), np.log(H[i]), np.log(H[i + 1])
        den = a - 2.0 * b + c
        d = 0.5 * (a - c) / den if den != 0.0 else 0.0
        out.append(float(f[i] + max(-1.0, min(1.0, d)) * df))
    if not bandwidths:
        return out
    bw = []
    for i in pk:
        half = H[i] / np.sqrt(2.0)
        a = i
        while a > 0 and H[a] > half:
            a -= 1
        b = i
        while b < n - 1 and H[b] > half:
            b += 1
        bw.append(float(f[b] - f[a]))
    return out, bw


UNIFORM = np.ones(SECTIONS)

if __name__ == '__main__':
    # THE ONE CASE WITH A CLOSED FORM: a tube closed at the glottis and open at
    # the lips is a quarter-wave resonator, so its formants land on odd
    # multiples of c/4L -- 500, 1500, 2500 for 17.5 cm. If the model cannot
    # reproduce that, nothing else it says is worth reading.
    got, bw = formants(UNIFORM, count=4, bandwidths=True)
    want = [C_SOUND / (4 * TRACT_CM) * m for m in (1, 3, 5, 7)]
    print("  uniform %.1f cm tube, %d sections" % (TRACT_CM, SECTIONS))
    print("   quarter-wave  %s" % ["%.0f" % v for v in want])
    print("   tube model    %s" % ["%.0f" % v for v in got])
    print("   error         %s" % ["%+.1f%%" % (100 * (g - w) / w)
                                   for g, w in zip(got, want)])
    print("   bandwidth     %s   (a real neutral tract: ~60, 90, 130)"
          % ["%.0f" % v for v in bw])


# ---------------------------------------------------------------------------
# Area functions
#
# Fitting 44 free areas to 3 formants is hopeless -- wildly underdetermined,
# and nothing keeps the result smooth or even positive. So the shape is
# carried by a few cosine modes of the LOG area, which is Story's
# parameterisation and has three properties we need: it is positive by
# construction, it is smooth (no section can spike away from its neighbours),
# and a handful of coefficients spans the vowel space. Interpolating the
# COEFFICIENTS is then interpolating a tract shape, which is the whole point.

def area_from_modes(coeffs, sections=SECTIONS):
    """A(x) = exp(sum_k c_k cos(k pi x)), x from glottis (0) to lips (1).

    The constant term is deliberately absent: only area RATIOS set reflection
    coefficients, so overall scale cannot move a formant.
    """
    x = (np.arange(sections) + 0.5) / sections
    g = np.zeros(sections)
    for k, c in enumerate(coeffs, start=1):
        g += c * np.cos(k * np.pi * x)
    return np.exp(g)


def _cents(a, b):
    return 1200.0 * np.log2(np.asarray(a, float) / np.asarray(b, float))


def fit_area(targets, modes=6, ridge=8.0, iters=220, tract_cm=TRACT_CM):
    """Find a tract shape whose resonances are `targets` (Hz).

    Levenberg-Marquardt on the mode coefficients, residuals in CENTS so a
    150 Hz error at F1 is not treated as the same mistake as 150 Hz at F3.
    The ridge term pulls toward the neutral tube: with 4 coefficients and 3
    targets the problem is underdetermined, and of the shapes that produce
    these formants we want the least contorted one.
    """
    targets = np.asarray(targets, float)
    c = np.zeros(modes)

    def resid(c):  # noqa: E306
        f = formants(area_from_modes(c), tract_cm, count=len(targets))
        if len(f) < len(targets):
            f = list(f) + [f[-1] if f else 200.0] * (len(targets) - len(f))
        return np.concatenate([_cents(f, targets), ridge * np.asarray(c)])

    try:
        from scipy.optimize import least_squares
    except ImportError:
        pass
    else:
        sol = least_squares(resid, c, diff_step=1e-3, xtol=1e-12, ftol=1e-12,
                            max_nfev=iters * (modes + 1))
        return sol.x, float(sol.cost * 2.0)

    r = resid(c)
    cost = float(r @ r)
    lam = 1e-3
    for _ in range(iters):
        J = np.zeros((len(r), modes))
        for j in range(modes):
            d = np.zeros(modes)
            d[j] = 1e-3
            J[:, j] = (resid(c + d) - r) / 1e-3
        A = J.T @ J
        g = J.T @ r
        step = None
        for _try in range(12):
            try:
                s = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), -g)
            except np.linalg.LinAlgError:
                lam *= 10.0
                continue
            r2 = resid(c + s)
            c2 = float(r2 @ r2)
            if c2 < cost:
                step, r, cost, lam = s, r2, c2, max(lam * 0.3, 1e-9)
                break
            lam *= 10.0
        if step is None:
            break
        c = c + step
        if np.linalg.norm(step) < 1e-7:
            break
    return c, cost


# No formant TRACKER lives here, and that is deliberate. The resonances of a
# tube are ordered and cannot cross, so the lowest three peaks are F1, F2, F3
# by construction. Matching each formant to its nearest neighbour in the next
# frame -- which looks like the careful thing to do -- is strictly worse: over
# a large step F3's new position can sit marginally closer to old F2 than F2's
# does, and the trajectory swaps two formants and never recovers. Ordering is
# the stronger invariant. (Near complete closure poles DO appear and disappear
# as cavities decouple, and there ordering is not enough -- see fit_stop.)


def trajectory(shapes, weights, count=3, tract_cm=TRACT_CM):
    """Formants of a blend of tract shapes -- the whole point of the module.

    `shapes` are mode coefficients; blending them blends a GEOMETRY, so every
    intermediate is a tract some throat could actually hold, and the formants
    move together because they are resonances of one object.
    """
    c = np.zeros(len(shapes[0]))
    for s, w in zip(shapes, weights):
        c = c + w * np.asarray(s)
    return formants(area_from_modes(c), tract_cm, count=count)


# ---------------------------------------------------------------------------
# The inventory, as SHAPES.
#
# Fitted by fit_area() to the formant targets in vowels.py, so the tube
# reproduces the vowels this renderer already sings -- exactly, to under a
# cent -- and nothing about the steady-state changes. What changes is that
# there is now a tract BETWEEN them.
#
# Worth noting what came out unbidden. Nobody typed in an anatomy; these were
# fitted to three numbers each. Yet /a/ lands narrow at the pharynx and wide
# at the mouth, /i/ the reverse with a hard palatal constriction, and /u/
# pinches to 0.26 cm2 at the lips -- which is lip rounding, and is what an MRI
# of a real singer shows. The formants were enough to recover the throat.

SHAPES = {
    'a':  (-1.27104, +0.03040, +0.63538, -0.04134, +0.25037, -0.03994,),   #  730 1090 2440
    'E':  (-0.24004, +0.00163, -0.43939, +0.00401, +0.07288, -0.00191,),   #  530 1840 2480
    'e':  (+0.18189, -0.00095, -0.75526, +0.00723, +0.06775, -0.00365,),   #  390 2100 2600
    'i':  (+0.62574, -0.01629, -1.23236, +0.02326, -0.19335, +0.00446,),   #  250 2520 3150
    'O':  (-1.10321, +0.37823, +0.78913, -0.36940, +0.39198, -0.40005,),   #  570  840 2410
    'o':  (-0.35109, +0.38000, +0.86211, -0.48902, +0.42750, -0.40147,),   #  400  750 2400
    'u':  (+0.37393, +0.08342, +0.79644, -0.35877, +0.45526, -0.26464,),   #  300  870 2240
    'y':  (+0.82244, -0.00501, -0.39590, +0.00509, +0.30448, -0.01796,),   #  300 1750 2200
    'P':  (+0.38579, -0.00198, -0.11574, -0.00172, +0.25859, -0.00606,),   #  400 1550 2200
    '@':  (-0.00210, +0.00001, -0.00116, +0.00002, -0.00107, +0.00002,),   #  500 1500 2500
    'A':  (-0.44314, +0.00017, +0.28982, -0.00346, +0.03012, -0.00167,),   #  600 1300 2500
    'V':  (-0.70188, +0.00285, +0.44809, -0.01021, +0.17276, -0.00772,),   #  640 1190 2390
    'alveolar': (+0.61780, -0.00285, -0.30407, +0.00332, -0.05301, +0.00126,),   #  350 1750 2600
    'glottal':  (-0.00210, +0.00001, -0.00116, +0.00002, -0.00107, +0.00002,),   #  500 1500 2500
    'labial':   (-0.24788, +0.29902, +0.78854, -0.36238, +0.50779, -0.38543,),   #  400  800 2200
    'palatal':  (+0.55636, -0.00791, -0.75748, +0.01313, -0.18597, +0.00456,),   #  320 2100 2900
    'velar':    (+0.41677, -0.00063, -0.68231, +0.00736, +0.20883, -0.01524,),   #  350 2000 2400
}


def shape_of(name):
    return np.asarray(SHAPES[name], float)


# ---------------------------------------------------------------------------
# Stops, as a closure in the same tube.
#
# The three burst classes were three separate empirical facts in vowels.py --
# velar COMPACT, alveolar diffuse-RISING, labial diffuse-FALLING -- each with
# its own hand-set centre and bandwidth. They are one fact.
#
# A burst is excited AT THE CONSTRICTION, not at the glottis: the pressure
# built up behind the closure escapes through it. So what filters it is the
# cavity IN FRONT of the closure, and the back cavity, sealed off behind a
# narrow constriction, contributes almost nothing. Front cavity length is
# therefore the whole story:
#
#   labial    closure at the lips     -> no front cavity -> no resonance,
#                                        a spectrum that only falls
#   alveolar  closure ~2 cm back      -> short cavity    -> high peak
#   velar     closure ~6-7 cm back    -> long cavity     -> low compact peak
#
# and "a velar burst tracks the following vowel's F2" needs no rule at all,
# because the front cavity is cut out of THAT VOWEL's own tract shape.

PLACE_X = {           # closure position, as a fraction from glottis to lips
    'labial': 0.99,
    'alveolar': 0.857,   # closure ~2.5 cm from the lips
    'palatal': 0.771,    # ~4 cm
    'velar': 0.657,      # ~6 cm
    'glottal': 0.02,
}


def constrict(coeffs, place, area=0.04, width=0.055, sections=SECTIONS):
    """The vowel's tract with a closure at `place`, as an area function.

    `area` is the residual opening in cm^2. It is deliberately NOT zero: a
    stop is heard at its RELEASE, when the articulators have already parted,
    and a fully sealed tube has no transfer function to speak of. It is also
    numerically kinder -- at total closure the front and back cavities
    decouple, poles appear and vanish, and formant identity stops meaning
    anything.
    """
    a = area_from_modes(coeffs, sections)
    x = (np.arange(sections) + 0.5) / sections
    p = PLACE_X.get(place, place) if isinstance(place, str) else place
    w = np.exp(-0.5 * ((x - p) / width) ** 2)
    return a * (1.0 - w) + area * w


def front_cavity(coeffs, place, sections=SECTIONS, **kw):
    """(areas, length_cm) of the tube in front of the closure."""
    p = PLACE_X.get(place, place) if isinstance(place, str) else place
    a = constrict(coeffs, place, sections=sections, **kw)
    i = int(round(p * sections))
    i = max(0, min(sections - 1, i))
    return a[i:], TRACT_CM * (sections - i) / sections


def burst(coeffs, place, freqs, tract_cm=TRACT_CM, sections=SECTIONS,
          source_hz=2400.0, source_order=3.0, wall=1.0, **kw):
    """The spectrum of a stop released at `place` before this vowel.

    The source is a flat noise puff at the constriction; this is the filter it
    passes through. Terminated at the closure end by a near-rigid wall,
    because that is what a constriction narrow enough to build pressure is.
    """
    f = np.asarray(freqs, float)
    # THE SOURCE HAS A BAND, and getting this wrong breaks both ends.
    #
    # It must FALL at the top, or a flat puff excites every front-cavity
    # resonance equally and a velar -- which has three below 8 kHz -- comes
    # out dominated by its highest and sounds alveolar.
    #
    # It must also fall at the BOTTOM. A release is a few milliseconds of a
    # small volume of air; it cannot make a 200 Hz component, and radiation
    # from the lips suppresses what little there is. Left flat down to DC, the
    # labial burst -- which has no resonance anywhere to compete -- peaked at
    # the bottom of the analysis range, which is a thump, not a /p/.
    #
    # What does NOT distinguish the three classes is this band. It is the same
    # puff in every case; the cavity in front of the closure is the difference.
    rise = f / (f + RADIATION_HZ)
    fall = 1.0 / (1.0 + (np.maximum(f, 1.0) / source_hz) ** source_order)
    a, L = front_cavity(coeffs, place, sections=sections, **kw)
    L *= tract_cm / TRACT_CM
    if len(a) < 2 or L < 0.25:
        # LABIAL: there is no front cavity. Nothing resonates, so the burst is
        # the bare source -- which is why a /p/ is diffuse and FALLING where a
        # /t/ is diffuse and rising. The one class that is an absence.
        return rise * fall
    # response() already carries the radiation load, so only the fall is added
    return response(a, f, tract_cm=L, glottal_r=0.92, wall=wall) * fall
