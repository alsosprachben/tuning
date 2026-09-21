"""Periodic amplitude modulation, downstream of the tone generator.

A Wurlitzer has a tremolo and a Rhodes suitcase has what its panel calls a
vibrato but is not one -- it is a STEREO PAN, the signal swinging between two
amplifiers rather than changing in level. Those look like two effects and are
one, which is what this module is for.

AM IS NOT A NEW PRIMITIVE HERE. The same argument leslie.py makes:

    (1 + m*cos(w t + ph)) * sin(W t + p)
      = sin(W t + p) + (m/2)*[ sin((W+w) t + p + ph) + sin((W-w) t + p - ph) ]

is three partials, and partials are what this renderer makes. So a tremolo is
one sideband pair per partial, and the carrier keeps its amplitude because the
modulator averages to one.

AND A PAN IS THE SAME PAIR WITH OPPOSITE SIGNS. If the left ear gets
(1 + m*cos) and the right gets (1 - m*cos), then the two ears' sidebands differ
only in sign -- so a stereo pan vibrato costs exactly what a mono tremolo
costs, and the difference between the two instruments is one minus sign.

It also falls out of that that the MONO SUM OF A PAN VIBRATO IS FLAT, which is
true of the real instrument: a Rhodes suitcase heard down one microphone has no
vibrato at all. aM is set to zero for the stereo sidebands for that reason, and
it is not an omission -- it is the effect.

WHERE IT SITS. After the amplifier and before the cabinet. On the real
instruments the modulation is in the preamp, ahead of the power amp, but both
voices that use this ship amp_drive = 0, so there is no valve between the two
places and the ordering is unobservable. It is placed after the amp anyway so
that a valve added later intermodulates the carrier rather than the sidebands,
which would be wrong; move this pass ahead of the amp at the same time.
"""
import math

import numpy as np


# Rates, in Hz, of the instruments that have one. Both are fixed on the real
# panel -- a Rhodes suitcase's rate knob moves, a Wurlitzer's does not -- and
# neither is fast enough to be heard as a pitch.
RHODES_HZ = 5.5
WURLITZER_HZ = 5.5

ENABLED = True


def expand(A, channels, sr, cols):
    """Give every partial of a modulated voice its sideband pair, in place.

    `channels` is {midi_channel: (rate_hz, depth, stereo)}. Depth is the
    fraction the level swings by, already scaled by whatever the file asked
    for; a depth of 0 emits nothing rather than emitting a silent pair.
    """
    if not ENABLED or not channels:
        return 0
    n = len(A['om'])
    extra = {k: [] for k in cols}
    made = 0
    for i in range(n):
        # 'mch' is the MIDI channel. leslie.py records what happens if this is
        # confused with 'ch', which is chiff: nothing expands, silently.
        ch = int(A['mch'][i])
        cfg = channels.get(ch)
        if cfg is None:
            continue
        rate, depth, stereo = cfg
        if depth <= 0.0 or rate <= 0.0:
            continue
        dw = 2.0 * math.pi * rate / sr
        half = 0.5 * depth
        for sign in (1.0, -1.0):
            for col in cols:
                extra[col].append(A[col][i])
            extra['om'][-1] = A['om'][i] + sign * dw
            extra['aL'][-1] = A['aL'][i] * half
            # The one minus sign that separates a pan from a tremolo.
            extra['aR'][-1] = A['aR'][i] * (-half if stereo else half)
            # A pan's mono sum is flat, and that is the effect, not a loss.
            extra['aM'][-1] = 0.0 if stereo else A['aM'][i] * half
            made += 1
    for k in cols:
        A[k].extend(extra[k])
    return made


def selftest():
    """The identity this module rests on, checked against a rendered waveform."""
    fails = []

    def check(name, ok, detail=""):
        print("   %-54s %s%s" % (name, "ok" if ok else "FAIL", detail))
        if not ok:
            fails.append(name)

    sr = 48000.0
    t = np.arange(int(sr)) / sr
    carrier, rate, depth = 220.0, 5.5, 0.6
    W, w = 2 * math.pi * carrier, 2 * math.pi * rate

    # The algebra: carrier plus a sideband pair IS the modulated wave.
    want = (1.0 + depth * np.cos(w * t)) * np.sin(W * t)
    got = (np.sin(W * t)
           + 0.5 * depth * np.sin((W + w) * t)
           + 0.5 * depth * np.sin((W - w) * t))
    err = float(np.max(np.abs(want - got)))
    check("a tremolo is a carrier and one sideband pair",
          err < 1e-9, "  (worst sample error %.1e)" % err)

    # And a pan is that pair sign-flipped: the two ears swing in opposition
    # while their sum stays exactly flat.
    L = np.sin(W * t) + 0.5 * depth * (np.sin((W + w) * t) + np.sin((W - w) * t))
    R = np.sin(W * t) - 0.5 * depth * (np.sin((W + w) * t) + np.sin((W - w) * t))
    env = lambda x: np.abs(np.convolve(np.abs(x), np.ones(64) / 64, 'same'))
    swing = lambda x: float(env(x)[1000:-1000].max() / env(x)[1000:-1000].min())
    s = float(np.max(np.abs((L + R) / 2.0 - np.sin(W * t))))
    check("a pan is that pair with the sign flipped in one ear",
          swing(L) > 2.0 and swing(R) > 2.0 and s < 1e-9,
          "  (each ear swings %.1fx, the mono sum by %.1e)" % (swing(L), s))

    # The table pass: one pair per row, and depth 0 costs nothing.
    cols = ('om', 'aL', 'aR', 'aM', 'mch', 'p0', 'p0R')
    def table(nrows=4):
        return {k: ([0.0] * nrows if k != 'mch' else [0.0] * nrows) for k in cols}
    A = table(); A['om'] = [0.1] * 4; A['aL'] = [1.0] * 4
    A['aR'] = [1.0] * 4; A['aM'] = [1.0] * 4
    made = expand(A, {0: (5.5, 0.6, True)}, sr, cols)
    check("one sideband pair per partial", made == 8 and len(A['om']) == 12,
          "  (%d rows added to 4)" % made)
    check("...and the pan's sidebands cancel in mono",
          all(v == 0.0 for v in A['aM'][4:]) and
          all(A['aL'][j] == -A['aR'][j] for j in range(4, 12)))
    A2 = table(); A2['om'] = [0.1] * 4; A2['aM'] = [1.0] * 4
    check("depth 0 emits nothing rather than a silent pair",
          expand(A2, {0: (5.5, 0.0, True)}, sr, cols) == 0)

    print("\n  %s" % ("all passed" if not fails else "FAILED: %s" % ", ".join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    import sys
    sys.exit(selftest())
