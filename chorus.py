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


def expand(A, channels, sr, cols=None, place=None):
    """Add each channel's chorus copies, in place. Returns partials added.

    `channels` is {channel: (send 0..1, cents tuple)} -- or (share, device,
    'gs') for a Sound Canvas file's chorus (gs_copies), whose copies `place`
    puts at its outputs."""
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
        if (send <= FLOOR and not (len(spec) > 3)) or not cents:
            continue
        rows = np.flatnonzero(mch == ch)
        if not len(rows):
            continue
        if len(spec) > 2 and spec[2] == 'pair':
            made += _pair(A, extra, keys, rows, cents, om, nf, p0, p0R, aL, aR, aM, sr)
            continue
        if len(spec) > 2 and spec[2] == 'gs':
            # A SOUND CANVAS FILE'S CHORUS (gs_copies), its copies from the
            # rows as they are, then the dry share
            # (copies of the channel's rows: a view of a typed column would
            # pin it, and the table grows below)
            P = {k: np.array(A[k])[rows] for k in keys}
            # (an insertion effect's mix follows the file: a share per row)
            sh = spec[3](P['non']) if len(spec) > 3 else send
            cps, dry = gs_copies(P, np.arange(len(rows)), cents, sh, sr, place)
            del P
            for _, o, sel in cps:
                for k in keys:
                    extra[k].extend(o[k].tolist())
                made += len(sel)
            dry = np.broadcast_to(np.asarray(dry, np.float64), (len(rows),))
            if cps and np.any(dry != 1.0):
                for k in ('aL', 'aR', 'aM'):
                    col = A[k]
                    for j, i in enumerate(rows):
                        col[int(i)] = col[int(i)] * float(dry[j])
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


# ---------------------------------------------------------------- the GS chorus
#
# A SOUND CANVAS FILE'S CHORUS IS ITS DEVICE, not a pedal's comb: one line,
# read by two taps -- its left and right outputs -- each swept by the same LFO
# in opposite phase, the line's output fed back into it (Cho Feedback). No
# copy is detuned: its pitch moves only as its delay does, exactly as a
# modulated delay line's does, which the kernel's vibrato columns are: a delay
# swinging +-A at rate r moves the frequency by 2 pi r A. A pass round the
# feedback loop is a further delay of the same swing, k passes k of each.
#
# Roland's eight macros and their values (SC-8850 owner's manual, "About
# Chorus Type"); the laws are GM 2's for the same controls, GM 2 having taken
# them from GS -- rate 0.122 Hz a step, depth (v+1)/3.2 ms of swing peak to
# peak, feedback 0.763 % a step. The DELAY's law is not published: 0.2 ms a
# step is chosen (Roland's 80, 16 ms; 127, 25 ms), as is the pre-LPF's corner
# (the delay's, gsdelay.device). The wet share is taken out of the dry, as
# CC93's is (expand): the send moves the mix, not the level.
GS_MACROS = {   # level, pre-LPF, feedback, delay, rate, depth, to reverb, to delay
    0: (64, 0, 0, 112, 3, 5, 0, 0),       # Chorus 1
    1: (64, 0, 5, 80, 9, 19, 0, 0),       # Chorus 2
    2: (64, 0, 8, 80, 3, 19, 0, 0),       # Chorus 3
    3: (64, 0, 16, 64, 9, 16, 0, 0),      # Chorus 4
    4: (64, 0, 64, 127, 2, 24, 0, 0),     # Feedback Chorus
    5: (64, 0, 112, 127, 1, 5, 0, 0),     # Flanger
    6: (64, 0, 0, 127, 0, 127, 0, 0),     # Short Delay
    7: (64, 0, 80, 127, 0, 127, 0, 0),    # Short Delay (FB)
}
GS_NAMES = ("Chorus 1", "Chorus 2", "Chorus 3", "Chorus 4", "Feedback Chorus", "Flanger",
            "Short Delay", "Short Delay (FB)")
GS_PARAM = {0x38: 'macro', 0x39: 'pre_lpf', 0x3A: 'level', 0x3B: 'feedback', 0x3C: 'delay',
            0x3D: 'rate', 0x3E: 'depth', 0x3F: 'to_reverb', 0x40: 'to_delay'}
GS_MAX_PASSES = 16
GS_TAPS = (('l', 0.0), ('r', np.pi))     # the outputs, and their LFO phases


def gs_device(params):
    """The chorus as the file set it: the macro's values (Chorus 3, as a GS
    reset leaves it), then each parameter it sent after."""
    m = int(params.get('macro', 2))
    lv, lpf, fb, dl, rt, dp, tr, td = GS_MACROS[m if m in GS_MACROS else 2]
    p = dict(level=lv, pre_lpf=lpf, feedback=fb, delay=dl, rate=rt, depth=dp,
             to_reverb=tr, to_delay=td)
    p.update({k: v for k, v in params.items() if k != 'macro'})
    swing = (p['depth'] + 1) / 3.2 / 1000.0 / 2.0      # seconds, either way
    rate = p['rate'] * 0.122
    return dict(tau=p['delay'] * 0.2 / 1000.0 + swing, rate=rate,
                vd=2.0 * np.pi * rate * swing, fb=min(0.99, p['feedback'] * 0.763 / 100.0),
                level=p['level'] / 127.0,
                lpf=(12000.0 * 2.0 ** (-p['pre_lpf'] / 1.5)) if p['pre_lpf'] else None)


def gs_copies(p, rows, dev, share, sr, place):
    """The GS chorus's copies of rows `rows` of p (columns as arrays):
    [(copy index, {column: array}, which of `rows` it copies)], and the dry
    factor the rows take (an array where `share` is one, per row). place
    is gsdelay's: (gL, gR, dL, dR samples) for an output and a frequency."""
    om = p['om'][rows].astype(np.float64)
    f = om * sr / (2.0 * np.pi)
    lp = 1.0 if not dev['lpf'] else 1.0 / np.sqrt(1.0 + (f / dev['lpf']) ** 2)
    non = p['non'][rows].astype(np.float64)
    aM = p['aM'][rows].astype(np.float64)
    ph0 = p['p0'][rows].astype(np.float64) + om * (non + p['delL'][rows].astype(np.float64))
    ph0R = p['p0R'][rows].astype(np.float64) + om * (non + p['delR'][rows].astype(np.float64))
    # the share over every pass round the loop, so feedback holds the level too
    fb2 = dev['fb'] ** 2
    passes = (1.0 - fb2 ** GS_MAX_PASSES) / (1.0 - fb2) if fb2 < 1.0 else float(GS_MAX_PASSES)
    share = np.asarray(share, np.float64)
    if not np.any(share > 0.0):
        return [], np.ones(len(rows)) if share.ndim else 1.0
    # THE DEVICE'S VOICES (a chorus type's: gsefx._chorus), else the system
    # chorus's two: (side, LFO phase[, extra delay s, depth factor])
    taps = dev.get('taps') or GS_TAPS
    wet = (share / float(len(taps)) / passes) ** 0.5
    out = []
    for ti, tap in enumerate(taps):
        side, phase = tap[0], tap[1]
        extra = tap[2] if len(tap) > 2 else 0.0
        dfac = tap[3] if len(tap) > 3 else 1.0
        pl = [place(side, x) for x in f]
        gl = np.array([q[0] for q in pl]); gr = np.array([q[1] for q in pl])
        dl = np.array([q[2] for q in pl]); dr = np.array([q[3] for q in pl])
        for k in range(1, GS_MAX_PASSES + 1):
            g = wet * dev['fb'] ** (k - 1)
            if np.all(np.abs(g) < FLOOR * 0.5) or (k > 1 and dev['fb'] == 0.0):
                break
            d = (k * dev['tau'] + extra) * sr
            o = {c: v[rows].copy() for c, v in p.items()}
            o['non'] = (non + d).astype(o['non'].dtype)
            o['noff'] = (p['noff'][rows].astype(np.float64) + d).astype(o['noff'].dtype)
            o['nfr'] = (o['non'].astype(np.float64) - np.floor(o['non'].astype(np.float64))).astype(o['nfr'].dtype)
            o['delL'] = dl.astype(o['delL'].dtype); o['delR'] = dr.astype(o['delR'].dtype)
            nn = o['non'].astype(np.float64)
            o['p0'] = (-om * (nn + dl) + ph0).astype(o['p0'].dtype)
            o['p0R'] = (-om * (nn + dr) + ph0R).astype(o['p0R'].dtype)
            if 'fmw' in o:
                fmw = p['fmw'][rows].astype(np.float64)
                o['fmp'] = (p['fmp'][rows] - fmw * d).astype(o['fmp'].dtype)
                o['fmpR'] = (p['fmpR'][rows] - fmw * d).astype(o['fmpR'].dtype)
            m = np.abs(aM) * g * lp
            o['aL'] = (m * gl).astype(o['aL'].dtype)
            o['aR'] = (m * gr).astype(o['aR'].dtype)
            o['aM'] = (aM * g * lp).astype(o['aM'].dtype)
            # the LFO runs free, as the device's does: its phase at the copy's onset
            o['vd'] = np.full(len(rows), min(0.5, k * dev['vd'] * dfac), o['vd'].dtype)
            o['vr'] = np.full(len(rows), dev['rate'], o['vr'].dtype)
            o['vp'] = ((2.0 * np.pi * dev['rate'] * nn / sr + phase) % (2.0 * np.pi)).astype(o['vp'].dtype)
            if 'vdl' in o:
                o['vdl'] = np.zeros(len(rows), o['vdl'].dtype)
            # ...only where it sounds: a row whose mix is 0 there makes no copy
            sel = np.flatnonzero(np.abs(np.broadcast_to(g, (len(rows),))) > 1e-12)
            if len(sel) < len(rows):
                o = {c: v[sel] for c, v in o.items()}
            if len(sel):
                out.append((ti * GS_MAX_PASSES + k, o, sel))
    return out, (1.0 - share) ** 0.5 if share.ndim else float((1.0 - share) ** 0.5)
