"""HALF-PEDALLING: the dampers between up and down.

The sustain pedal was a switch at 64 (live.py's CC64, blockrender's _PED_CH).
A real one is not: between "dampers off" and "dampers on the strings" there is
a band of pedal travel where the felt only touches -- and what that does is
measured (Lehtonen, Askenfelt & Valimaki, "Analysis of the part-pedaling effect
in the piano", JASA 126(2) EL49, 2009, a Steinway C): not a fixed extra decay
but a LEVEL LIMIT. The string rings free, then decays fast while its swing is
bigger than the gap under the damper, then rings on nearly free once it fits
(mostly the horizontal polarisation, which the felt barely touches). In the
middle register the level drops and the fundamental stays; the highs go first.

So, per key:
  contact(p, key)   0 free .. 1 the damper fully down, from the pedal's value:
                    smooth across a BAND of it -- the fuzzy threshold. The bass
                    dampers are heavier and lift later (Yamaha US7521626: they
                    are the last off and the first back), so the band sits
                    higher in the bass. 0 and 127 are always outside it, so a
                    file of switch values never enters it.
  threshold_db(c)   the level (dB re the note's forte strike) the gap lets ring
                    at contact c: +inf at 0, -inf at 1.
  track(...)        a released note's CUMULATIVE extra damping in dB at its
                    fundamental, at each block edge: R(c) a second while its
                    level is over the threshold, a residual under it.
  weight(nf, f0)    the same damping at a partial: (nf/f0)^BETA -- the felt
                    takes the highs first.

Full contact is not modelled here: there the damper has landed, and the note
ends as it always did (its release, noff + re). This is only the band between.
The numbers are a starting point, to be voiced by ear (Ben); Lehtonen gives
the shape, not a felt's rates.
"""
import math

import numpy as np

# THE BAND, in CC64 values: contact 1 at its lower edge, 0 at its upper. At the
# top damped key and at A0; between, by key. VSL's half-pedal range is 26-102
# and ondine.mid writes 24..104 in steps of 16.
BAND_TREBLE = (24.0, 88.0)
BAND_BASS = (40.0, 104.0)
LOW_KEY = 21

# The damper on a string, fully down: the piano's release_valve_time stops it
# over ~0.12 s, about 60 dB -- 500 dB a second. Partial contact presses less.
FULL_DB_S = 500.0
# ...and under the gap, what the felt still takes (the horizontal polarisation
# ringing past it): a fraction of the above rate, scaled by contact too
RESIDUAL = 0.02
# The gap's level: at contact 1/2 the string rings on below -KNEE_DB
KNEE_DB = 24.0
# The highs go first: the extra damping at a partial, as (f / f0) ** BETA
BETA = 0.5

# ...each overridable for a take that exaggerates it (TUNING_DAMPER_KNEE_DB,
# TUNING_DAMPER_FULL_DB_S): the ear learns the effect from the overdone one
import os as _os
KNEE_DB = float(_os.environ.get("TUNING_DAMPER_KNEE_DB", KNEE_DB))
FULL_DB_S = float(_os.environ.get("TUNING_DAMPER_FULL_DB_S", FULL_DB_S))

LN10_20 = math.log(10.0) / 20.0


def band(key, top=89):
    """(lower, upper) CC64 edges of the band for this key."""
    x = min(max((key - LOW_KEY) / float(max(top - LOW_KEY, 1)), 0.0), 1.0)
    lo = BAND_BASS[0] + (BAND_TREBLE[0] - BAND_BASS[0]) * x
    hi = BAND_BASS[1] + (BAND_TREBLE[1] - BAND_BASS[1]) * x
    return lo, hi


def contact(p, key, top=89):
    """0 (free) .. 1 (damper down) for pedal value p (0-127) on this key. A key
    at or above `top` has no damper: always 0."""
    if key >= top:
        return 0.0
    lo, hi = band(key, top)
    x = min(max((float(p) - lo) / (hi - lo), 0.0), 1.0)
    return 1.0 - x * x * (3.0 - 2.0 * x)


def threshold_db(c):
    """The level the gap lets ring, dB re the key's forte strike."""
    if c <= 0.0:
        return math.inf
    if c >= 1.0:
        return -math.inf
    return -KNEE_DB * c / (1.0 - c)


def rate_db_s(c, over):
    """The extra damping a second at contact c: full while the string's swing
    is over the gap, the residual under it."""
    r = FULL_DB_S * c
    return r if over else r * RESIDUAL


def track(edges, pedal_at, key, level_db, top=89):
    """A released note's damping through the band.

    edges     block-edge times (s), increasing, from the key-up on
    pedal_at  t -> the pedal value (0-127) in force at t
    level_db  t -> the note's own (undamped) level at t, dB re a forte strike
              of its key -- so a loud note is damped down to the same gap a
              soft one is, as a string is
    Returns (DC, full): DC[i] the cumulative extra damping (dB at the
    fundamental) at edges[i], 0 at the first; `full` the first edge at which
    contact is 1 (the damper landed: the note's release starts there), or None.
    Each block takes the contact at its start."""
    edges = np.asarray(edges, float)
    dc = np.zeros(len(edges))
    full = None
    acc = 0.0
    for i in range(len(edges) - 1):
        c = contact(pedal_at(edges[i]), key, top)
        if c >= 1.0:
            full = edges[i]
            dc[i:] = acc
            return dc, full
        if c > 0.0:
            over = level_db(edges[i]) - acc > threshold_db(c)
            acc += rate_db_s(c, over) * (edges[i + 1] - edges[i])
        dc[i + 1] = acc
    if len(edges) and contact(pedal_at(edges[-1]), key, top) >= 1.0:
        full = edges[-1]
    return dc, full


def weight(nf, f0):
    """dB of damping at frequency nf per dB at the fundamental f0, as the
    natural-log factor the kernel multiplies by (gain = exp(-weight * DC))."""
    return LN10_20 * (np.maximum(np.asarray(nf, float), 1e-6) / max(float(f0), 1e-6)) ** BETA


def selftest(verbose=True):
    fails = []

    def check(name, ok, detail=""):
        if verbose:
            print("   %-62s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    keys = range(21, 89)
    check("0 and 127 never in the band, on any key",
          all(contact(0, k) == 1.0 and contact(127, k) == 0.0 for k in keys))
    mono = all(contact(p, k) >= contact(p + 1, k) for k in keys for p in range(127))
    check("contact falls as the pedal goes down, on every key", mono)
    check("the bass dampers lift later", contact(64, 21) > contact(64, 60) > contact(64, 88),
          "(contact at 64: A0 %.2f, C4 %.2f, E6 %.2f)" % (contact(64, 21), contact(64, 60), contact(64, 88)))
    check("no damper from damper_top up", contact(0, 89) == 0.0 and contact(0, 100) == 0.0)
    check("the gap opens with the pedal", threshold_db(0.25) > threshold_db(0.5) > threshold_db(0.75))
    # A HAND COMPUTATION: a held level of -6 dB, contact 1/2 (threshold -24):
    # 250 dB/s until 18 dB are gone (72 ms), then 5 dB/s
    k = 60
    lo, hi = band(k)
    p_half = next(p / 100.0 for p in range(int(lo * 100), int(hi * 100))
                  if contact(p / 100.0, k) <= 0.5)
    c = contact(p_half, k)
    edges = np.arange(0, 0.5, 128 / 48000.0)
    dc, full = track(edges, lambda t: p_half, k, lambda t: -6.0)
    t_cross = (-6.0 - threshold_db(c)) / (FULL_DB_S * c)
    i = np.searchsorted(edges, t_cross)
    after = (dc[-1] - dc[i + 1]) / (edges[-1] - edges[i + 1])
    check("over the gap the full rate, under it the residual",
          full is None and abs(dc[i] - (-6.0 - threshold_db(c))) < FULL_DB_S * c * 128 / 48000.0 + 1e-9
          and abs(after - FULL_DB_S * c * RESIDUAL) < 1e-6,
          "(contact %.3f: %.1f dB gone by %.0f ms, then %.2f dB/s)" % (c, dc[i], 1000 * t_cross, after))
    dc2, full2 = track(edges, lambda t: 127.0 if t < 0.1 else 0.0, k, lambda t: -6.0)
    check("dampers off: nothing; landing: the release takes over",
          dc2[-1] == 0.0 and full2 is not None and abs(full2 - 0.1) < 128 / 48000.0 + 1e-9)
    w = weight([261.6, 523.2, 1046.4], 261.6)
    check("the highs go first", w[0] < w[1] < w[2] and abs(w[0] - LN10_20) < 1e-12)
    if verbose:
        print("\n  %s" % ("all passed" if not fails else "FAILED: %s" % ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
