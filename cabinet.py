#!/usr/bin/env python3
"""The speaker cabinet, and why it is a pass and not a body.

An electric guitar's amplifier is not the end of the chain -- the loudspeaker
is, and it is the least linear-sounding link in it. A 12" guitar speaker is not
a monitor that happens to be in a box: it is a deliberately bad, deliberately
coloured transducer with a cone resonance near 100 Hz, a presence peak in the
low treble where the cone starts breaking up, and a very steep roll-off above
about 4 kHz. Everything a guitarist means by "the amp sounds like" is mostly it.

IT MATTERS MOST WHERE THERE IS DISTORTION. A clipped signal has harmonics all
the way to Nyquist, and a real cabinet throws nearly all of them away. Rendered
without one, the products `tubeamp` correctly produces at 8 and 12 kHz are all
audible, and the result is a wasp rather than an overdriven amplifier. This is
the difference between distortion that is right and distortion that is usable.

WHY THIS IS A PASS OVER THE FINISHED TABLE, and not a FormantBody on the voice
class. FormantBody is already a cabinet in everything but name -- resonances,
antiresonances, a top corner, a low cutoff, and a normalisation that keeps a
peak a colour rather than a level. But a body is applied in `harmonic_volume`,
while a note's own partials are being built, and that is BEFORE
`tubeamp.expand` runs. A cabinet there would filter the clean signal and every
distortion product added afterwards would bypass it entirely, which is the
exact failure described above. The signal chain is

    string -> pluck comb -> pickup comb -> AMP -> CABINET -> room

and the order is the whole point, so this stands between the amplifier pass and
the rotor pass in blockrender.

It still uses FormantBody's arithmetic, because that arithmetic is right and
already written.

THE REFLECTIONS GET IT TOO. The room's images were computed from the clean
partials long before the amplifier ran, and a cabinet colours the SOURCE -- so
the room has to hear the coloured version. This scales every row on the
channel, direct and reflected alike. It is a filter on frequency, and a
reflection has the same frequency as the sound it is a copy of.
"""
import numpy as np

import tonelib as T


class Cabinet(T.FormantBody):
    """A loudspeaker's response, as a gain on a partial's frequency.

    Normalised at `ref_hz` rather than by FormantBody's `_bore_norm`, which
    answers a different question: that one preserves the total power of a
    harmonic SERIES as the note moves, because a body filter should not decide
    how loud a note is. A cabinet is not per-note at all -- it sits at fixed
    frequencies while everything slides through it -- so what it must not do is
    change the overall level, and holding the midrange at unity says exactly
    that.
    """
    ref_hz = 1000.0

    def __init__(self):
        self._ref = float(super().bore_gain(self.ref_hz))

    def gain(self, hz):
        hz = np.maximum(np.asarray(hz, float), 1e-6)
        return self.bore_gain(hz) / self._ref

    def response_db(self, freqs):
        """For the report, and for the fizz test -- see examples/guitar.py."""
        g = self.gain(np.asarray(freqs, float))
        return 20.0 * np.log10(np.maximum(g, 1e-12))


class Guitar12(Cabinet):
    """One 12" guitar speaker in an open-backed cabinet.

    The shape, and where each number comes from:

      110 Hz peak    the cone/box resonance. Below it the speaker stops
                     coupling and a 6-string's low E fundamental is already
                     on the slope, which is why a guitar cabinet sounds
                     smaller than its bandwidth suggests.
      1.1 kHz dip    the upper-mid notch between the piston band and cone
                     breakup. Shallow, but it is the hollow a guitar speaker
                     has and a full-range driver does not.
      2.4 kHz peak   cone breakup -- "presence", "bite". The thing that makes
                     a distorted guitar cut through a mix.
      4.2 kHz, 4th   the top roll-off, and THE most consequential number here.
                     It is what separates an overdriven amplifier from fizz.
      85 Hz, 2nd     the low roll-off.

    Rendered flat to 1 kHz, this gives +6.6 dB at 2.4 kHz, -8.9 at 5 kHz,
    -23.2 at 8 kHz and -30.7 at 10 kHz, which is the right order for a
    Celestion-class 12" and sets the top three octaves of a clipped signal
    where they belong: audible as brightness, not as a separate insect.
    """
    formants = ((110.0, 90.0, 0.55), (2400.0, 1600.0, 0.85))
    antiformants = ((1100.0, 700.0, 0.25),)
    formant_floor = 0.55
    bore_corner_hz = 4200.0
    bore_order = 4.0
    bell_cutoff_hz = 85.0
    bell_order = 2.0


CABINETS = {"guitar12": Guitar12()}


def get(name):
    """A cabinet by name, or None. Unknown names are an error, not silence --
    a misspelt cabinet that quietly rendered flat would be very hard to hear."""
    if not name:
        return None
    try:
        return CABINETS[name]
    except KeyError:
        raise KeyError("unknown cabinet %r; have %s"
                       % (name, ", ".join(sorted(CABINETS))))


def expand(A, channels, sr=None, cols=None):
    """Put every partial of a cabinet voice through the speaker, in place.

    Adds no partials -- unlike the amplifier and the rotor, a loudspeaker
    creates nothing, it only fails to pass things. Returns how many rows it
    touched, for the report.
    """
    if not channels or not len(A.get('nf', ())):
        return 0
    mch = np.asarray(A['mch'])
    nf = np.asarray(A['nf'], float)
    aL = np.asarray(A['aL'], float)
    aR = np.asarray(A['aR'], float)
    aM = np.asarray(A['aM'], float)
    done = 0
    for ch, name in channels.items():
        cab = get(name)
        if cab is None:
            continue
        sel = (mch == ch)
        if not sel.any():
            continue
        g = cab.gain(nf[sel])
        aL[sel] *= g
        aR[sel] *= g
        aM[sel] *= g
        done += int(sel.sum())
    if done:
        A['aL'][:] = aL.tolist()
        A['aR'][:] = aR.tolist()
        A['aM'][:] = aM.tolist()
    return done
