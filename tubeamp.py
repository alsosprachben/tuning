#!/usr/bin/env python3
"""The Leslie's amplifier, as partials.

A 122 is 40 W of push-pull tubes, and the growl of a driven Hammond is the
thing an organ makes audible that a clean model cannot fake. What makes it hard
here is that synthkernel.c is ADDITIVE -- it accumulates outL[n] += per partial
-- so a waveshaper has nowhere to stand: a nonlinearity acts on the SUM, which
exists only after every partial has been added.

But distortion products ARE partials. A nonlinearity applied to a sum of
cosines produces more cosines, at sums and differences of the input
frequencies, with amplitudes that follow analytically from the transfer
function's power series. So the amplifier does not need a sample-domain stage;
it needs to emit the partials it creates, before the rotor does, which is the
signal order a real cabinet has.

WHY NOT JUST GIVE EACH PARTIAL ITS OWN HARMONICS. Because that is true of one
tone and false of a chord, and a Hammond is a chord machine. Measured on a
tempered Hammond chord through a soft clipper, only 27% of the distortion
energy lands on harmonics of the inputs; the other 73% is INTERMODULATION
between them. That is what the drawbars beating against each other through the
nonlinearity sounds like, and modelling harmonics alone would miss nearly all
of it.

WHERE THIS STOPS, WHICH IS EARLIER THAN HOPED. The series is an expansion
about the operating point, and it holds only while the signal stays inside the
grid bias. Measured against the real curve it tracks to 2.6% at drive 1.0 with
three orders and 0.8% with nine -- and then DIVERGES: at drive 1.6, fifteen
orders is 132% wrong, worse than three. The tube cuts off at |v| = bias, and a
power series about zero cannot have a corner at any order.

So this models the BEND and not the CLIP. At the edge of cutoff, twenty
partials through the stage make distortion about 50 dB down -- warmth, an
amplifier being worked, audible as thickening rather than as growl. Leslie
overdrive proper is the clip, and it is out of reach here twice over: past the
radius of convergence, and combinatorially anyway, since fifth order over
twenty partials is some 680,000 products. That is a real ceiling on the
partial-domain approach and not a tuning problem.

WHY IT IS AFFORDABLE. Two reasons. A Hammond's tonewheels are SHARED -- a
drawbar patches in another wheel of the tempered scale rather than synthesising
a harmonic -- so a four-note chord on nine drawbars has 1015 partials but only
84 distinct frequencies. And a third-order product's amplitude is A_i*A_j*A_k,
so weak partials make cubically weak products: keeping the strongest 20 carries
91.6% of the distortion energy, the strongest 14 carries 76%. Truncating by
amplitude is not a convenience, it is the ordering the physics already imposes.
"""
import math

# Child-Langmuir: a triode's plate current follows the 3/2 power of its grid
# drive. This is the law, not a curve chosen to sound right -- which matters,
# because the shape of the bend IS the difference between an amplifier and a
# fuzz box, and a tanh has a different one.
EXPONENT = 1.5

# The quiescent grid bias, in units of the drive. The series below is an
# expansion about this point and holds while the signal stays inside it; past
# it the tube cuts off, which is a hard corner no power series reaches.
BIAS = 1.0

# How far the two halves of the push-pull pair are mismatched. Zero is a
# perfectly balanced stage, and a perfectly balanced stage has NO EVEN ORDERS
# AT ALL -- they cancel between the halves. So the second harmonic is not a
# parameter here; it is what a real pair's imbalance produces, and it arrives
# only because this is non-zero.
IMBALANCE = 0.06


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


# Below this a difference tone is not a tone. Two partials a hair apart make a
# product at a fraction of a hertz, which as a PARTIAL is a DC offset -- in a
# real amplifier that same near-coincidence is heard as the two of them beating,
# which the two of them are already doing. Emitting it again as its own partial
# adds an offset and no sound.
MIN_HZ = 20.0

# Peak over rms for a dense sum of partials with independent phases. Used to
# say how hard the valve is actually being driven, since `drive` is defined
# against the grid bias and the bias is a PEAK voltage.
CREST = 3.0


def products(freqs, amps, phases, coeffs, keep=20, floor=1e-4, nyquist=None):
    """Every distortion partial: [(freq, amp, phase)].

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


def expand(A, channels, sr, cols, keep=20, floor=1e-5):
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
    extra = {k: [] for k in cols}
    made = 0
    for ch, drive in channels.items():
        if drive <= 0.0:
            continue
        # Past the bias the series does not merely lose accuracy, it diverges,
        # so asking for more drive than the valve has range would emit
        # confident nonsense rather than a louder growl.
        drive = min(float(drive), 1.0)
        rows = np.flatnonzero((mch == ch) & (dr > 0.5))
        if len(rows) < 2:
            continue
        # The drive is carried by the normalisation below, not by the
        # coefficients: scaling the input and scaling the coefficients are the
        # same statement, and doing both would square it.
        cs = series()
        edges = np.unique(np.concatenate([non[rows], noff[rows]]))
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < sr * 0.01:            # shorter than 10 ms: no partner
                continue
            live = rows[(non[rows] <= a + 1e-6) & (noff[rows] >= b - 1e-6)]
            if len(live) < 2:
                continue
            amp = aM[live]
            order = np.argsort(-amp)[:keep]
            sel = live[order]
            fs = (om[sel] * sr / (2.0 * np.pi)).tolist()
            # THE SERIES IS IN UNITS OF THE VALVE'S OWN GRID BIAS, and the
            # partials are in units of whatever the renderer's absolute scale
            # happens to be -- about 1e-5 here. Feeding those straight in makes
            # every third-order product 1e-15 and the amplifier does nothing at
            # all, silently, which is exactly what it did the first time.
            #
            # So the segment is normalised so its peak sits at `drive` times the
            # bias: drive 1.0 means the signal just reaches the point where a
            # 3/2-law triode starts to bend, which is the edge of breakup. The
            # products come back out through the same scale.
            # PEAK, NOT THE SUM OF THE AMPLITUDES. Adding them is the
            # all-in-phase worst case, which a dense sum of partials never
            # reaches: with independent phases the crest factor settles near 3
            # times the rms, so summing them underdrives the valve by about a
            # factor of two -- and a factor of two at the input is a factor of
            # eight in every third-order product.
            rms = float(np.sqrt(0.5 * (aM[sel].astype(float) ** 2).sum()))
            peak = (CREST * rms) or 1.0
            unit = drive / peak
            as_ = (aM[sel] * unit).tolist()
            ps = np.asarray(A['p0'], float)[sel]
            # p0 anchors phase at sample 0, so the phase AT THIS SEGMENT is
            # p0 + om*a -- using p0 alone would give every segment the phase it
            # would have had at the start of the piece.
            ps = (ps + om[sel] * a).tolist()
            src = int(sel[0])
            for f, g, ph in products(fs, as_, ps, cs, keep=keep,
                                     floor=floor, nyquist=sr * 0.5):
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
                g = g / unit                 # back into the renderer's scale
                sc = g / max(A['aM'][src], 1e-12)
                extra['aL'][-1] = A['aL'][src] * sc
                extra['aR'][-1] = A['aR'][src] * sc
                extra['aM'][-1] = g
                made += 1
    for k in cols:
        A[k].extend(extra[k])
    return made
