#!/usr/bin/env python3
"""GM2 CC93 chorus: copies of the source a few cents away, swept slowly.

WHAT A CHORUS IS, AND WHAT IT IS NOT. A bucket-brigade chorus takes ONE
oscillator and makes a small number of copies at FIXED offsets, each swept by
its own slow low-frequency oscillator. A string section has many players whose
spread is random, per player and per note, and who never agree. This file
implements the first. The codebase makes that distinction three times already
-- the accordion's musette, the string machine, the synth brass -- and calls it
systematic against drawn.

So CC93 is not "more players". It is the ARP-string-machine effect: a fixed
comb, deliberately placed, which is why it can be a pass over the finished
partial table at all. A detune normally cannot be, because a detune lives in
the partials' FREQUENCIES and those are written once -- but here the offsets
are constants chosen in advance and only the wet GAIN follows the controller.

The copies carry their own vibrato columns rather than extra partials, which is
the same trick leslie.expand uses for its Doppler: the sweep that makes a
bucket-brigade breathe costs nothing, because the kernel already modulates a
partial's frequency from vd/vr/vp.

THE OFFSETS ARE THE VOICE'S OWN where it has them. A synth string machine, a
synth pad and a synth brass each declare `chorus_cents` already, because the
chorus is part of what those instruments ARE. Anything else gets a plain pair,
which is what a chorus pedal in front of an instrument does.
"""
import numpy as np

# A chorus pedal's own comb, for a voice that does not carry one. Two copies,
# a few cents either side: wide enough to hear, narrow enough not to sound out
# of tune. Cents, not Hz -- a fixed Hz offset is a different interval in every
# register, which is a detuned unison rather than a chorus.
DEFAULT_CENTS = (-7.0, 7.0)

# How fast each copy is swept, and how far. A BBD chorus modulates its delay
# at well under a hertz; the copies must not agree, or the comb marches in
# step and reads as a phaser instead.
SWEEP_HZ = (0.21, 0.29, 0.17, 0.34)
SWEEP_DEPTH = 0.0016            # fraction of the frequency, ~2.8 cents

# THE COPIES ARE DELAYED, as a bucket brigade's are: that is what it is, a
# delay line swept a little. Without it every copy began each note IN PHASE
# with its parent -- the phase anchor scaled with the frequency -- so every
# note opened coherent, 2 or 3 copies summing to a peak, and fell as they
# drifted apart: measured, a held square fell 12 dB in a second and a saw 5,
# heard as a decay on every note (Ben: "the leads seem to have a decay").
# A delay turns each harmonic of the copy by a different angle, so the sum
# starts where it will stay: a shimmer, not a fade. Different per copy, and
# in the BBD range.
DELAY_S = (0.007, 0.011, 0.013, 0.017)

# Below this the copy is inaudible against its parent and is not worth a row.
# Same argument as leslie's lobe gates: spending partials on what cannot be
# heard multiplies the table for nothing.
FLOOR = 0.02


# A DETUNED PAIR (tonelib detuned_pair: GS's Detuned EP / Detuned Organ) is not
# a chorus: the GM sets build it as their sample TWICE, a few cents either way,
# each half-way to its own side -- no sweep, no dry. So the note itself is the
# lower copy, placed left, and one copy is made above it, placed right, by
# LEVEL as a sample player pans (power held); the copy delayed as a chorus's,
# so the two do not open in phase.
PAIR_PAN = 0.5


def pair_side(side):
    """(left gain, right gain) for a copy `side` (-1 left, +1 right) of a pair,
    each at half power."""
    s = PAIR_PAN * side
    return (0.5 * (1.0 - s)) ** 0.5, (0.5 * (1.0 + s)) ** 0.5


def offsets_for(props):
    """The comb this voice wants, in cents."""
    cents = tuple(getattr(props, 'chorus_cents', ()) or ())
    return cents if cents else DEFAULT_CENTS


def expand(A, channels, sr, cols=None):
    """Add each channel's chorus copies, in place. Returns partials added.

    `channels` is {channel: (send 0..1, cents tuple)}.
    """
    if not channels or not len(A.get('nf', ())):
        return 0
    mch = np.array(A['mch'])
    om = np.array(A['om'], float)
    nf = np.array(A['nf'], float)
    p0 = np.array(A['p0'], float)
    p0R = np.array(A['p0R'], float)
    aL = np.array(A['aL'], float)
    aR = np.array(A['aR'], float)
    aM = np.array(A['aM'], float)
    keys = list(cols or A.keys())
    extra = {k: [] for k in keys}
    made = 0
    for ch, spec in channels.items():
        send, cents = spec[0], spec[1]
        if send <= FLOOR or not cents:
            continue
        rows = np.flatnonzero(mch == ch)
        if not len(rows):
            continue
        if len(spec) > 2 and spec[2] == 'pair':
            made += _pair(A, extra, keys, rows, cents, om, nf, p0, p0R, aL, aR, aM, sr)
            continue
        # A SEND IS A MIX, NOT AN ADDITION. Copies are incoherent with their
        # parent, so their powers add: two at full send made the channel 3.5 dB
        # LOUDER, and a controller that raises the level while it is asked for
        # an effect is a controller nobody can use. So the wet share is taken
        # OUT of the dry one and the total is held:
        #
        #     dry^2 + n * wet^2 = 1,  wet^2 / (dry^2 + n*wet^2) = send
        #
        # which is the same separation of colour from level that the bore
        # filter and the head shadow both keep, and the same decision taken for
        # CC91: distance sets the ratio, never the loudness.
        wet = (send / float(len(cents))) ** 0.5
        dry = (1.0 - send) ** 0.5
        gain = wet
        # Read the parents' amplitudes BEFORE the dry scaling below, so the
        # copies are made from the sound as it was.
        for ci, c in enumerate(cents):
            ratio = 2.0 ** (c / 1200.0)
            keep = rows[nf[rows] * ratio < sr * 0.5]
            if not len(keep):
                continue
            rate = SWEEP_HZ[ci % len(SWEEP_HZ)]
            delay = DELAY_S[ci % len(DELAY_S)]
            for i in keep:
                for k in keys:
                    extra[k].append(A[k][int(i)])
                # Frequency scales and the phase anchor scales with it, since
                # p0 = -om*(non + delay) and om has just been multiplied.
                extra['om'][-1] = om[i] * ratio
                extra['nf'][-1] = nf[i] * ratio
                # ...and then turned by the line's delay at the copy's own
                # frequency, which is what delaying it does to its phase.
                # (om is radians per SAMPLE, so the delay goes in samples.)
                extra['p0'][-1] = p0[i] * ratio - om[i] * ratio * delay * sr
                extra['p0R'][-1] = p0R[i] * ratio - om[i] * ratio * delay * sr
                extra['aL'][-1] = aL[i] * gain
                extra['aR'][-1] = aR[i] * gain
                extra['aM'][-1] = aM[i] * gain
                # ...and its own slow sweep, which costs no partials.
                extra['vd'][-1] = SWEEP_DEPTH
                extra['vr'][-1] = rate
                extra['vp'][-1] = 2.0 * np.pi * (ci / float(len(cents)))
                made += 1
        # ...and the dry share comes down by what the wet took.
        if made and dry != 1.0:
            for k in ('aL', 'aR', 'aM'):
                col = A[k]
                for i in rows:
                    col[int(i)] = col[int(i)] * dry
    for k in keys:
        A[k].extend(extra[k])
    return made


def _pair(A, extra, keys, rows, cents, om, nf, p0, p0R, aL, aR, aM, sr):
    """A detuned pair over these rows: themselves moved down and left, a copy
    up and right. Returns the copies made."""
    lo, hi = 2.0 ** (cents[0] / 1200.0), 2.0 ** (cents[1] / 1200.0)
    gl0, gr0 = pair_side(-1)
    gl1, gr1 = pair_side(+1)
    made = 0
    delay = DELAY_S[0]
    for i in rows:
        i = int(i)
        if nf[i] * hi < sr * 0.5:
            for k in keys:
                extra[k].append(A[k][i])
            extra['om'][-1] = om[i] * hi
            extra['nf'][-1] = nf[i] * hi
            extra['p0'][-1] = p0[i] * hi - om[i] * hi * delay * sr
            extra['p0R'][-1] = p0R[i] * hi - om[i] * hi * delay * sr
            extra['aL'][-1] = aL[i] * gl1
            extra['aR'][-1] = aR[i] * gr1
            extra['aM'][-1] = aM[i] * 0.5 ** 0.5
            made += 1
        A['om'][i] = om[i] * lo
        A['nf'][i] = nf[i] * lo
        A['p0'][i] = p0[i] * lo
        A['p0R'][i] = p0R[i] * lo
        A['aL'][i] = aL[i] * gl0
        A['aR'][i] = aR[i] * gr0
        A['aM'][i] = aM[i] * 0.5 ** 0.5
    return made
