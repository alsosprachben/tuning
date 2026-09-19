#!/usr/bin/env python3
"""The Leslie's amplifier, as partials.

A 122 is 40 W of push-pull tubes, and the growl of a driven Hammond is the
thing an organ makes audible that a clean model cannot fake. What makes it hard
here is that synthkernel.c is ADDITIVE -- it accumulates outL[n] += per partial
-- so a waveshaper has nowhere to stand: a nonlinearity acts on the SUM, which
exists only after every partial has been added.

But distortion products ARE partials. A nonlinearity applied to a sum of
cosines produces more cosines, at sums and differences of the input
frequencies. So the amplifier does not need a sample-domain stage; it needs to
emit the partials it creates, before the rotor does, which is the signal order
a real cabinet has.

WHY NOT JUST GIVE EACH PARTIAL ITS OWN HARMONICS. Because that is true of one
tone and false of a chord, and a Hammond is a chord machine. Measured on a
tempered Hammond chord through a soft clipper, only 27% of the distortion
energy lands on harmonics of the inputs; the other 73% is INTERMODULATION
between them. That is what the drawbars beating against each other through the
nonlinearity sounds like, and modelling harmonics alone would miss nearly all
of it.

HOW THE PRODUCTS ARE FOUND, AND WHY NOT BY A SERIES. The first version expanded
the transfer function as a power series and enumerated the products term by
term. That reaches the BEND and stops there, for two separate reasons:

  - The series is an expansion about the operating point and holds only inside
    the grid bias. At drive 1.0 three orders track the real curve to 2.6%; at
    drive 1.6 fifteen orders is 132% wrong, WORSE than three. The tube cuts off
    at |v| = bias and a power series about zero cannot have a corner.
  - Even inside the radius it is combinatorial. Fifth order over twenty
    partials is some 680,000 terms and seventh is 42 million, and a clip needs
    those orders: hard-clipping a tonewheel chord puts 4.0% of the distortion
    energy in third order, 46.7% in fifth and 41.9% in seventh.

Both of those are properties of EXPANDING, not of the problem. So the curve is
now evaluated instead: synthesise the segment's partials, apply the valve per
sample, subtract the linear part, and transform. The FFT finds every product of
every order at once, for any transfer function, in N log N -- no series, no
radius of convergence, no enumeration. `series` and `products` are kept below
because the analytic result is the only independent check on the numerical one.

WHY THIS WORKS AS WELL AS IT DOES, WHICH WAS A SURPRISE. Counting terms is
misleading; what matters is how many distinct FREQUENCIES they land on, and
they collapse. Drawbar ratios are tempered approximations to integers (the
"third harmonic" is 2.9966), and sums and differences of near-integers are
near-integers, so the whole product set falls onto a near-harmonic lattice.
One key on nine drawbars at seventh order is 403,779 terms but 7,969 distinct
frequencies in 610 clusters ten cents wide, and 92% of them sit within 25 cents
of a half-harmonic of the key.

A chord is where that could have broken and does not. At fifth order a triad
has 1,155,020 distinct product frequencies and a triad with a seventh has
5,068,131 -- but the cluster counts are 1,113 and 1,153. Equal temperament
keeps cross-products between different keys on the same lattice. Five million
lines inside eleven hundred groups is about a thousand lines per cluster, all
beating against each other.

THAT IS THE GROWL. A cluster of a thousand near-coincident lines is a dense
chorus around a definite pitch, not noise -- it stays correlated with the
source and Dopplers coherently through the rotor, which noise would not -- and
it is why the growl has pitch at all. A window too short to resolve inside a
cluster reports the cluster's aggregate, at the right pitch and with the right
energy, which is the right level of description and not merely a cheap one: a
much LONGER window returns a million individually meaningless lines and
measures worse. WINDOW_S has an optimum rather than a maximum, and 1.0 s is
where it was measured.

WHAT IS LOST, AND WHY NOTHING RECOVERS IT. A cluster emitted as one partial
carries the right energy at the right pitch but not the beating inside it. The
obvious repair -- emit each peak as several partials spread over its measured
width -- was tried and is WORSE (waveform error 59.5% to 70.2% on a chord),
because arbitrary detuning is worse than none. A shaped noise bed does not help
either, for the reason the growl has pitch: noise is uncorrelated with the
source and a cluster is not. So the spectrum is right (1/12-octave bands to
10-15%, total energy to 1%) and the slow beat inside a cluster is not there.
"""
import math

# Child-Langmuir: a triode's plate current follows the 3/2 power of its grid
# drive. This is the law, not a curve chosen to sound right -- which matters,
# because the shape of the bend IS the difference between an amplifier and a
# fuzz box, and a tanh has a different one.
EXPONENT = 1.5

# The quiescent grid bias, in units of the drive. Drive 1.0 puts the signal's
# peak here, which is where cutoff begins on one half of the pair.
BIAS = 1.0

# How far the two halves of the push-pull pair are mismatched. Zero is a
# perfectly balanced stage, and a perfectly balanced stage has NO EVEN ORDERS
# AT ALL -- they cancel between the halves. So the second harmonic is not a
# parameter here; it is what a real pair's imbalance produces, and it arrives
# only because this is non-zero.
IMBALANCE = 0.06

# THE OTHER END OF THE CURVE, without which this cannot clip at all. Cutoff
# alone is only half a clipper: past the bias one half stops conducting and the
# other is left growing as v^1.5, so the stage goes EXPANSIVE -- measured, the
# slope fell to 0.718 at drive 1 and came back up to 1.008 by drive 3, which is
# a stage getting louder per volt the harder it is hit.
#
# A real stage flattens at the top too, because the conducting half runs out:
# the plate voltage swings down toward the cathode and the load line hits the
# knee, so plate current stops following the grid. So each half's current is
# passed through a soft ceiling
#     i -> imax * u / (1 + u^k)^(1/k),  u = i/imax
# which is i for small i, imax for large, with `k` setting how sharp the corner
# is -- k -> infinity is a hard clip. Same shape as the pipe end-correction
# saturation in tonelib (a quantity that stops growing rather than one that
# grows without bound), and it is the ceiling, not the cutoff, that makes the
# odd orders a clip needs.
# CEILING is set so the two limits do NOT coincide. A push-pull stage reaches
# grid cutoff before the plate runs out of swing, and the numbers say the same:
# with the ceiling at the cutoff current (about 3x quiescent) drive 1.0 lands
# slope 0.30, which would have silently re-voiced every existing amp_drive --
# drive 1.0 has always meant the EDGE of breakup here. At 6x it means that
# still (slope 0.62 against 0.72 for cutoff alone) and the clip arrives above
# it: 0.43 at drive 2, 0.07 at drive 4.
CEILING = 6.0      # peak plate current, in units of the quiescent current
KNEE = 3.0         # sharpness of the corner; larger is harder

# LIVE BUILDS ITS TEMPLATES THROUGH blockrender, one note at a time, so with
# this on every template arrives carrying that note's own distortion baked in
# -- and live then adds the chord's on top of it, counting the single-note part
# twice. Live turns it off while it builds, the same way it turns off the
# rotor's sidebands and for the same reason: offline has one stateless call to
# put everything in, live has a callback and can do it properly later.
ENABLED = True

# Below this a difference tone is not a tone. Two partials a hair apart make a
# product at a fraction of a hertz, which as a PARTIAL is a DC offset -- in a
# real amplifier that same near-coincidence is heard as the two of them beating,
# which the two of them are already doing. Emitting it again as its own partial
# adds an offset and no sound.
MIN_HZ = 20.0

# Peak over rms for a dense sum of partials with independent phases. Only the
# analytic path needs this: the numerical path synthesises the signal and so
# can MEASURE its peak instead of estimating it. Kept because `products` is
# still the reference the numerical path is checked against.
CREST = 3.0

# Length of the analysis window, in seconds. See the module docstring: this is
# a model parameter with an optimum, not a resolution to be maximised, and 1.0
# is where it was measured. Shorter loses real structure -- at 0.25 s two
# genuine products 2.7 Hz apart, which BEAT with a 370 ms period, collapse into
# one line and the beating with them. Longer is worse again: waveform error
# over a fixed horizon went 65% (0.5 s), 53% (1.0 s), 60% (2.0 s) on one key,
# because past the point where the products are resolved the extra bins only
# add ways for a frequency estimate to be dragged off.
WINDOW_S = 1.0

# Analysis runs at this multiple of the sample rate. A clip makes harmonics far
# above Nyquist and a real amplifier does not fold them back down; sampling the
# curve at sr would alias them into the audible band and emit them as partials
# that the analog circuit never produced.
#
# Measured, there is very little to fold: 0.0007% of the residual sits above
# 22 kHz even at drive 6, because a soft knee never makes a true corner and its
# harmonics fall off geometrically. 1 and 4 gave identical errors to four
# figures. 2 is kept as margin -- KNEE is a parameter, and a harder one puts
# more up there -- at 129 ms a segment against 324 for 4.
OVERSAMPLE = 2

# How many peaks to emit per segment, and the level below which a peak is not
# worth a partial (relative to the loudest).
# Raising this to 1200 moved the chord's waveform error from 59.5% to 56.5%
# and tripled the partial count, which is not a trade worth making.
KEEP_PEAKS = 400
PEAK_FLOOR = 1e-3

# LIVE runs the same code at a lower setting, because `apply` is called on the
# audio callback thread and a 128-frame block at 44.1 kHz is 2.9 ms. Measured
# on a four-note chord: the offline setting is 54.7 ms (13.9% band error), and
# 0.25 s at no oversampling with 150 peaks is 6.7 ms (16.4%) -- a sixth of a dB
# worse per band for an eighth of the cost. Still far too slow for a block, so
# the caller computes it OFF the audio thread and stamps the result on it.
LIVE_WINDOW_S = 0.25
LIVE_OVERSAMPLE = 1
LIVE_KEEP = 150

# Most partials a segment's signal is synthesised from. Unlike the analytic
# path this cap is about COST ONLY and the cost is linear, not combinatorial --
# and partials sharing a frequency are combined first, which on a Hammond is
# most of them (a four-note chord on nine drawbars is 1015 partials and 84
# distinct frequencies).
KEEP_PARTIALS = 96

# A MEASURED NEGATIVE, kept because the idea is a tempting one. The clusters
# are real -- a four-note chord's fifth-order products are five million lines
# inside about 1,100 groups ten cents wide -- so emitting each peak as several
# detuned partials carrying its width, rather than as one line, ought to
# reproduce the beating inside it. It does not. Split into equal-energy groups
# the waveform error went from 59.5% to 70.2% on a chord and 52.6% to 54.4% on
# one key: the sub-partials get subdivision frequencies and mismatched phases,
# and detuning that is merely arbitrary is worse than none. One partial
# carrying the cluster's whole energy at the cluster's own peak is better.
#
# What a cluster costs is therefore not energy (that is exact, see `emit`) but
# the beating inside it, and no noise bed recovers that either -- noise is
# uncorrelated with the source and a cluster is not.

def _binom(a, n):
    """C(a, n) for real a -- the Taylor coefficient of (1+x)^a."""
    out = 1.0
    for k in range(n):
        out *= (a - k) / (k + 1)
    return out


def series(order=5, bias=BIAS, imbalance=IMBALANCE):
    """[c1, c2, ... c_order] of the push-pull stage about its operating point.

    One half sees +v on a bias of a, the other -v on a bias of b, and their
    plate currents are subtracted:

        f(v) = (a + v)^1.5 - (b - v)^1.5

    so the nth coefficient is C(1.5, n) * [a^(1.5-n) - (-1)^n * b^(1.5-n)].
    With a == b the bracket vanishes for every even n, which is the whole point
    of a push-pull pair and is why the even orders here are a consequence of
    `imbalance` rather than something dialled in.

    Normalised so c1 == 1: the small-signal gain is a level, not a colour.

    NOT USED FOR RENDERING any more -- `curve` is evaluated instead. This is
    the reference the numerical path is verified against at low drive, where
    the series is accurate and the two must agree.
    """
    a = bias * (1.0 + imbalance)
    b = bias * (1.0 - imbalance)
    cs = []
    for n in range(1, order + 1):
        c = _binom(EXPONENT, n) * (a ** (EXPONENT - n)
                                   - ((-1.0) ** n) * b ** (EXPONENT - n))
        cs.append(c)
    c1 = cs[0] or 1.0
    return [c / c1 for c in cs]


def curve(v, bias=BIAS, imbalance=IMBALANCE, ceiling=CEILING, knee=KNEE):
    """The valve's transfer function, evaluated rather than expanded.

    Each half is a 3/2-law triode with a floor and a ceiling: it stops
    conducting when the grid swings past the bias, and its plate current stops
    rising when the load line reaches the knee. The two are subtracted, which
    is what makes a balanced pair's even orders cancel.

    Accepts a scalar or an array. The quiescent point is removed, so an
    unbalanced pair's standing offset is not emitted as DC.
    """
    import numpy as np
    a = bias * (1.0 + imbalance)
    b = bias * (1.0 - imbalance)
    imax = ceiling * bias ** EXPONENT

    def half(g, bi):
        i = np.maximum(bi + g, 0.0) ** EXPONENT
        u = i / imax
        return imax * u / (1.0 + u ** knee) ** (1.0 / knee)

    v = np.asarray(v, float)
    y = half(v, a) - half(-v, b)
    q = float(half(np.float64(0.0), a) - half(np.float64(0.0), b))
    return y - q


def small_signal(**kw):
    """d(curve)/dv at the operating point -- the gain the stage has when clean.

    Subtracting this times the input is what leaves a pure distortion residual,
    and doing it in the TIME domain (rather than notching the input frequencies
    out of the spectrum afterwards) is exact, because the input is not measured
    but synthesised: its linear image is known to machine precision.
    """
    h = 1e-5
    return float((curve(h, **kw) - curve(-h, **kw)) / (2.0 * h))


def _window(n):
    """Blackman-Harris, 4-term: -92 dB sidelobes.

    The sidelobe level is the whole reason for the choice. A strong input
    partial sits 60-80 dB over the products being looked for, so with a plainer
    window its own leakage skirt would be picked as distortion -- the analysis
    would report products that are an artefact of the transform.
    """
    import numpy as np
    k = 2.0 * np.pi * np.arange(n) / n
    return (0.35875 - 0.48829 * np.cos(k)
            + 0.14128 * np.cos(2.0 * k) - 0.01168 * np.cos(3.0 * k))


def combine(freqs, amps, phases, tol=0.01):
    """Merge partials sharing a frequency into one, as complex amplitudes.

    A Hammond's tonewheels are SHARED -- a drawbar patches in another wheel of
    the tempered scale rather than synthesising a harmonic -- so a chord names
    the same frequency many times over. Two cosines at one frequency ARE one
    cosine, and adding them here rather than in the synthesis loop is both
    cheaper and the only way the amplitude driving the valve is right: three
    drawbars on one wheel drive it three times as hard, unless they cancel.
    """
    import numpy as np
    f = np.asarray(freqs, float)
    key = np.round(f / tol).astype(np.int64)
    z = np.asarray(amps, float) * np.exp(1j * np.asarray(phases, float))
    uk, inv = np.unique(key, return_inverse=True)
    acc = np.zeros(len(uk), complex)
    np.add.at(acc, inv, z)
    fsum = np.zeros(len(uk))
    np.add.at(fsum, inv, f)
    cnt = np.bincount(inv, minlength=len(uk)).astype(float)
    return (fsum / cnt), np.abs(acc), np.angle(acc)


def emit(freqs, amps, phases, sr, drive, window_s=WINDOW_S,
         oversample=OVERSAMPLE, keep=KEEP_PEAKS, floor=PEAK_FLOOR,
         stats=None, **valve):
    """Distortion partials from the curve itself: [(freq, amp, phase)].

    Amplitudes go in and come out in the caller's units; the scaling into and
    out of the valve's own (where 1.0 is the grid bias) happens here.

    THE PEAK IS MEASURED, NOT ESTIMATED. `drive` is defined against the bias
    and the bias is a peak voltage, so the signal has to be scaled by its peak
    -- and the first version summed the amplitudes instead, the all-in-phase
    worst case a dense sum never reaches, which underdrove the stage by about a
    factor of two and left the amplifier 50 dB down and inaudible. The analytic
    path had to guess at a crest factor (CREST, about 3x rms). This one does
    not have to guess: it synthesises the signal, so it can look.
    """
    import numpy as np
    f = np.asarray(freqs, float)
    a = np.asarray(amps, float)
    p = np.asarray(phases, float)
    if len(f) < 2:
        return []

    n0 = int(round(window_s * sr))
    n = 1 << max(8, int(math.ceil(math.log(max(n0, 1), 2))))
    n *= int(oversample)
    fs = sr * float(oversample)
    t = np.arange(n) / fs

    # The signal going into the valve. Cost is O(partials * samples): LINEAR,
    # which is the thing the series could not be, and the reason there is no
    # longer any physical need to throw away quiet partials. Accumulated in a
    # loop rather than broadcast, because the (partials x samples) matrix is
    # tens of megabytes and is read exactly once.
    x = np.zeros(n)
    for A, F, P in zip(a, f, p):
        x += A * np.cos(2.0 * np.pi * F * t + P)
    pk = float(np.abs(x).max())
    if pk <= 0.0:
        return []
    unit = drive * BIAS / pk
    x *= unit
    g = small_signal(**valve)
    r = curve(x, **valve) - g * x
    r -= r.mean()

    w = _window(n)
    R = np.fft.rfft(r * w)
    e = np.abs(R) ** 2
    df = fs / n
    lim = int(min(sr * 0.5, fs * 0.5) / df)
    if lim < 8:
        return []
    e = e[:lim]

    # THE DISTRIBUTION COMES FROM THE FFT, THE LEVEL FROM THE TIME DOMAIN, and
    # they have to be taken separately because the residual is NOT STATIONARY.
    # Distortion fires at the crests, where the partials happen to align, and a
    # window of a second holds only a handful of those -- so whether a crest
    # lands under the taper or under the flat of the window changes the
    # apparent energy. Measured on a four-note chord the window-weighted total
    # ran 29% over the true residual power, and the first version emitted 131%
    # of the distortion actually present. The unwindowed Parseval sum has no
    # such bias, so it sets the level and the spectrum only says where it goes.
    X0 = np.fft.rfft(r)
    power = float(2.0 * (np.abs(X0[1:lim]) ** 2).sum()) / (n * n)

    # Peaks: local maxima, strongest first, down to `floor` of the strongest.
    inner = e[1:-1]
    loc = np.flatnonzero((inner > e[:-2]) & (inner >= e[2:])) + 1
    if not len(loc):
        return []
    loc = loc[e[loc] > e[loc].max() * floor ** 2]
    if not len(loc):
        return []
    if len(loc) > keep:
        loc = loc[np.argsort(-e[loc])[:keep]]
    loc = np.sort(loc)

    # Every bin goes to its nearest peak, so no energy falls between the
    # cracks: a peak stands for its whole neighbourhood, not just its tip.
    k = np.arange(len(e))
    j = np.searchsorted(loc, k)
    jl = np.clip(j - 1, 0, len(loc) - 1)
    jr = np.clip(j, 0, len(loc) - 1)
    own = np.where(np.abs(loc[jl] - k) <= np.abs(loc[jr] - k), jl, jr)
    order = np.argsort(own, kind='stable')
    bounds = np.searchsorted(own[order], np.arange(len(loc) + 1))

    out = []
    for c in range(len(loc)):
        bins = order[bounds[c]:bounds[c + 1]]
        tote = float(e[bins].sum())
        if tote <= 0.0:
            continue
        km = int(loc[c])
        # FREQUENCY FROM THE TIP, ENERGY FROM THE WHOLE REGION. Taking both
        # from the region -- an energy centroid over every assigned bin -- lets
        # whatever is nearby drag the centre off, and a frequency error costs
        # more the longer the segment runs, because the phase walks away from
        # it. Measured over a 1.5 s horizon the centroid was 100% wrong on a
        # single key where the parabolic tip was 80%.
        if 0 < km < len(e) - 1:
            y0, y1, y2 = (0.5 * math.log(max(e[km + d], 1e-300))
                          for d in (-1, 0, 1))
            den = y0 - 2.0 * y1 + y2
            gc = km + (max(-0.5, min(0.5, 0.5 * (y0 - y2) / den))
                       if den != 0.0 else 0.0)
        else:
            gc = float(km)
        hz = gc * df
        if hz < MIN_HZ or hz >= sr * 0.5:
            continue
        # THE WINDOW PUTS A PHASE RAMP ON EVERY OFF-BIN COMPONENT. The window
        # is symmetric about (n-1)/2 rather than about zero, so a component d
        # bins off its peak arrives with an extra 2*pi*d*(n-1)/(2n) of phase --
        # up to pi/2 at half a bin. Reading the peak bin's angle and attaching
        # it to an interpolated frequency left the spectrum right and the
        # waveform uncorrelated, which is what it sounded like it would be.
        ph = (float(np.angle(R[km]))
              - 2.0 * np.pi * (gc - km) * (n - 1) / (2.0 * n))
        out.append((hz, math.sqrt(tote), ph))

    # Scale to the measured residual power. Energy conservation is then exact
    # by construction, which means the question worth asking of this is not
    # "does it conserve" but "is the energy in the right PLACES" -- the
    # waveform error, not the total.
    have = sum(am * am for _, am, _ in out) * 0.5
    sc = math.sqrt(power / have) / unit if have > 0.0 else 0.0
    out = [(hz, am * sc, ph) for hz, am, ph in out]
    if stats is not None:
        stats['power'] = power
        stats['peaks'] = len(loc)
        stats['emitted'] = len(out)
        stats['drive_peak'] = float(np.abs(x).max())
    return out


def products(freqs, amps, phases, coeffs, keep=20, floor=1e-4, nyquist=None):
    """Every distortion partial to third order, analytically: [(f, amp, ph)].

    THE REFERENCE, NOT THE RENDERER. `emit` replaced this: it reaches every
    order rather than three, needs no radius of convergence, and costs one FFT
    instead of a combinatorial sum. What this still does is provide an
    independent answer at low drive, where three orders are accurate -- the two
    must agree there, and if they do not it is the numerical path's windowing,
    interpolation or calibration that is wrong.

    `freqs`/`amps`/`phases` describe the partials going in, as COSINES, which
    is what the kernel renders. The expansions are the ordinary ones:

        cos A cos B       = 1/2 [cos(A-B) + cos(A+B)]
        cos A cos B cos C = 1/4 [cos(A+B+C) + cos(A+B-C)
                                 + cos(A-B+C) + cos(-A+B+C)]

    with the multiplicity of each unordered multiset carried in front -- 6 for
    three distinct partials, 3 when two coincide, 1 when all three do.

    The terms that land back on an input frequency are kept rather than
    discarded: third order puts 1.5*A_i^2*A_j on omega_j, which is the gain
    compression that makes a driven amplifier feel like one. Dropping them
    would leave the distortion without the squeeze that goes with it.
    """
    n = len(freqs)
    idx = sorted(range(n), key=lambda i: -amps[i])[:keep]
    out = []
    c2 = coeffs[1] if len(coeffs) > 1 else 0.0
    c3 = coeffs[2] if len(coeffs) > 2 else 0.0

    def add(f, a, p):
        if abs(a) < floor or f < MIN_HZ:
            return
        if nyquist and f >= nyquist:
            return
        # cos(-x) == cos(x): a product folded below zero comes back with its
        # phase negated, not as a negative frequency.
        out.append((f, a, p))

    if c2:
        for ii in range(len(idx)):
            i = idx[ii]
            add(2.0 * freqs[i], 0.5 * c2 * amps[i] ** 2, 2.0 * phases[i])
            for jj in range(ii + 1, len(idx)):
                j = idx[jj]
                g = c2 * amps[i] * amps[j]
                add(freqs[i] + freqs[j], g, phases[i] + phases[j])
                d = freqs[i] - freqs[j]
                add(abs(d), g, phases[i] - phases[j] if d >= 0
                    else phases[j] - phases[i])
    if c3:
        for ii in range(len(idx)):
            i = idx[ii]
            ai, fi, pi = amps[i], freqs[i], phases[i]
            add(3.0 * fi, 0.25 * c3 * ai ** 3, 3.0 * pi)
            add(fi, 0.75 * c3 * ai ** 3, pi)
            for jj in range(len(idx)):
                if jj == ii:
                    continue
                j = idx[jj]
                aj, fj, pj = amps[j], freqs[j], phases[j]
                g = 0.75 * c3 * ai * ai * aj
                add(2.0 * fi + fj, g, 2.0 * pi + pj)
                d = 2.0 * fi - fj
                add(abs(d), g, 2.0 * pi - pj if d >= 0 else pj - 2.0 * pi)
                add(fj, 1.5 * c3 * ai * ai * aj, pj)      # compression
            for jj in range(ii + 1, len(idx)):
                j = idx[jj]
                for kk in range(jj + 1, len(idx)):
                    k = idx[kk]
                    g = 1.5 * c3 * amps[i] * amps[j] * amps[k]
                    fs = (freqs[i], freqs[j], freqs[k])
                    ps = (phases[i], phases[j], phases[k])
                    for sg in ((1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1)):
                        f = sum(s * v for s, v in zip(sg, fs))
                        p = sum(s * v for s, v in zip(sg, ps))
                        add(abs(f), g, p if f >= 0 else -p)
    return out


def expand(A, channels, sr, cols, keep=KEEP_PARTIALS, floor=PEAK_FLOOR):
    """Emit the amplifier's distortion partials, in place on the table.

    Runs BEFORE leslie.expand, which is the whole reason this can live in the
    partial domain at all: the amp is upstream of the rotor in a real cabinet,
    and here that is simply the order of two passes rather than an argument
    about where a waveshaper can stand.

    THE LIFETIME OF A PRODUCT IS THE INTERSECTION OF ITS PARENTS'. A product
    exists only while every partial that makes it is sounding, so it starts
    with the last of them and stops with the first of them to go. That is why a
    chord growls and a single note does not, and getting it wrong leaves
    distortion ringing through a chord change that has already happened.

    So the piece is cut at every note boundary on the channel, and products are
    formed per segment. A partial that spans two chords contributes to both,
    with different partners each time.
    """
    import numpy as np
    if not channels:
        return 0
    mch = np.asarray(A['mch'])
    dr = np.asarray(A['dr'])
    non = np.asarray(A['non'], float)
    noff = np.asarray(A['noff'], float)
    om = np.asarray(A['om'], float)
    aM = np.asarray(A['aM'], float)
    p0 = np.asarray(A['p0'], float)
    extra = {k: [] for k in cols}
    made = 0
    for ch, drive in channels.items():
        if drive <= 0.0:
            continue
        # NO LONGER CLAMPED AT THE BIAS. The old ceiling was the series'
        # radius of convergence, not the amplifier's: past it the expansion
        # diverged and the only honest thing was to refuse. The curve is
        # evaluated now, so drive past cutoff is simply the clip, which is
        # what a driven Leslie is.
        drive = float(drive)
        rows = np.flatnonzero((mch == ch) & (dr > 0.5))
        if len(rows) < 2:
            continue
        edges = np.unique(np.concatenate([non[rows], noff[rows]]))
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < sr * 0.01:            # shorter than 10 ms: no partner
                continue
            live = rows[(non[rows] <= a + 1e-6) & (noff[rows] >= b - 1e-6)]
            if len(live) < 2:
                continue
            fs = om[live] * sr / (2.0 * np.pi)
            # p0 anchors phase at sample 0, so the phase AT THIS SEGMENT is
            # p0 + om*a -- using p0 alone would give every segment the phase it
            # would have had at the start of the piece.
            ps = p0[live] + om[live] * a
            fs, as_, ps = combine(fs, aM[live], ps)
            if len(fs) < 2:
                continue
            if len(fs) > keep:
                sub = np.argsort(-as_)[:keep]
                fs, as_, ps = fs[sub], as_[sub], ps[sub]
            src = int(live[int(np.argmax(aM[live]))])
            for f, g, ph in emit(fs.tolist(), as_.tolist(), ps.tolist(),
                                 sr, drive, floor=floor):
                for k in cols:
                    extra[k].append(A[k][src])
                w = 2.0 * math.pi * f / sr
                extra['om'][-1] = w
                extra['nf'][-1] = f
                extra['non'][-1] = int(a)
                extra['noff'][-1] = int(b)
                # back out an anchor at sample 0 from the phase wanted at `a`
                extra['p0'][-1] = ph - w * a
                extra['p0R'][-1] = ph - w * a
                sc = g / max(A['aM'][src], 1e-12)
                extra['aL'][-1] = A['aL'][src] * sc
                extra['aR'][-1] = A['aR'][src] * sc
                extra['aM'][-1] = g
                made += 1
    for k in cols:
        A[k].extend(extra[k])
    return made
