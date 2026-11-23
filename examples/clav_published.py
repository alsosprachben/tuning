#!/usr/bin/env python3
"""THE CLAVINET FROM ITS PUBLISHED MEASUREMENTS (2026-11-22, licences.md L10:
Aalto's companion-page takes, the first reference, are no longer read).

    python3 -I examples/clav_published.py            the targets, printed
    python3 -I examples/clav_published.py length      the speaking-length law
    python3 -I examples/clav_published.py decay [--maxfev=N]   fit the ring to the loss filter
    python3 -I examples/clav_published.py measure    ours against every target
    python3 -I examples/clav_published.py register [--maxfev=N]   the register level, even
    python3 -I examples/clav_published.py keyup     the key-up's level re the strike

THE SOURCES (one Hohner D6 "in mint condition", the authors'):
  [E] Gabrielli, Valimaki, Penttinen, Squartini, Bilbao, "A digital
      waveguide-based approach for Clavinet modeling and synthesis", EURASIP
      J. Adv. Signal Process. 2013:103 (open access, CC BY).
  [I] Gabrielli, Valimaki, Bilbao, "Real-time emulation of the Clavinet",
      ICMC 2011, pp. 249-252.
  [D] Remaggi, Gabrielli et al., "A pickup model for the Clavinet", DAFx-12.
  Strings: Hohner's original plain gauge .008" (Electric Piano Forum, 2017:
  "The unwound/plain strings are .009 gauge instead of the original .008").

WHAT EACH GIVES
  STIFFNESS  [E] Table 1: B at six keys, "linearly interpolated" between.
  THE RING   [I] s3.1: the loop's one-pole loss filter, "gain ... constant to
             0.996 for all the keys, while the pole coefficient ... linearly
             interpolated over the whole keyboard range, showing a monotonic
             increase from -0.8 to -0.1" (by the authors' ear on the
             instrument). Its loss a period at harmonic n, times f0, is that
             harmonic's dB/s (fs 44.1 kHz).
  THE LADDER [E] p.4: "The second partial always has a magnitude more than
             3 dB higher than the first, and often ... the third is higher
             than the second" -- a CHECK, not a fit (measure prints it). Fitted
             with the tilt alone it drove tonal_dampening below zero: every
             harmonic to the 128th growing, far past hearing, the output
             saturating (Ben: "They clip a lot"). An ordinary falling tilt
             already gives h2 over h1 in the bass and middle; the top
             octave's dip is its pickup's notch (q ~0.36 of a short string).
             The tilt is Ben's ear's, of three (clav_tilt_*.mp3).
  LENGTH     [D] 67.8 cm at 161 Hz. Plain strings: B = pi^2 E d^2 / (64 rho
             L^4 f^2) (steel), so [E]'s B at F#5 and E6 with d .008" gives L
             there. Wound bass: [E] Fig. 3's A#2 pickup take notches "every
             5th partial", "approximately 544 Hz and multiple frequencies" --
             the centre pickup at 544/116.5 of the length.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

# [E] Table 1: (key, B)
B_TABLE = ((29, 5e-4), (34, 2e-4), (50, 9e-5), (51, 1e-4), (78, 9e-5), (88, 8e-5))
LOOP_GAIN = 0.996                       # [I]
POLE = ((29, -0.8), (88, -0.1))         # [I], linear over the keys F1-E6
FS_LOOP = 44100.0
STEEL_E, STEEL_RHO = 2.0e11, 7850.0
PLAIN_D = 0.008 * 0.0254                # Hohner's original plain gauge
REF_L, REF_HZ = 0.678, 161.0            # [D]
A2S_HZ, A2S_NOTCH_HZ = 116.54, 544.0    # [E] Fig. 3, A#2
WOUND = 23                              # [E]: "the first 23 strings wound", F1 up


def hz(k):
    return 440.0 * 2 ** ((k - 69) / 12.0)


def B_at(key):
    ks, bs = zip(*B_TABLE)
    return float(np.interp(key, ks, bs))


def pole_at(key):
    (k0, a0), (k1, a1) = POLE
    return a0 + (a1 - a0) * min(1.0, max(0.0, (key - k0) / (k1 - k0)))


# THE RIPPLE FILTER in the same loop ([E] s3.1: z^-R + r, R = Rrate L, "randomly
# chosen at each keystroke ... between 1/2 to 1/3 and -0.006 to -0.001"):
# "The T60 values for the first two partials have been matched with the ripple
# filter" ([E] Fig. 8) -- it lengthens the lowest partials. Averaged over its
# ranges, as a key struck many times hears it.
RIPPLE_R = (1 / 3.0, 1 / 2.0)
RIPPLE_r = (-0.006, -0.001)


def ripple_db(n, steps=41):
    """the ripple's mean gain a period at harmonic n, dB (positive: it sustains)"""
    acc = 0.0
    for i in range(steps):
        rr = RIPPLE_R[0] + (RIPPLE_R[1] - RIPPLE_R[0]) * i / (steps - 1)
        for j in range(steps):
            r = RIPPLE_r[0] + (RIPPLE_r[1] - RIPPLE_r[0]) * j / (steps - 1)
            acc += 10 * math.log10(1 + 2 * r * math.cos(2 * math.pi * n * rr) + r * r)
    return acc / steps ** 2


def ring_dbs(key, n):
    """[I]'s loop -- its loss filter and [E]'s ripple -- harmonic n's loss a
    period, dB, times f0: dB/s"""
    f0 = hz(key)
    w = 2 * math.pi * n * f0 / FS_LOOP
    a = pole_at(key)
    mag = LOOP_GAIN * (1 + a) / math.sqrt(1 + 2 * a * math.cos(w) + a * a)
    return (-20 * math.log10(mag) - ripple_db(n)) * f0


def plain_length(key):
    """a plain steel string's speaking length from its stiffness and gauge"""
    f = hz(key)
    return (math.pi ** 2 * STEEL_E * PLAIN_D ** 2 / (64 * STEEL_RHO * B_at(key) * f * f)) ** 0.25


def centre_m(key, c0=0.185, c1=0.065):
    return c0 + (c1 - c0) * min(1.0, max(0.0, (key - 29.0) / 59.0))


def length_law():
    """(power over REF_HZ, power under it): plain strings from B, the wound
    bass from [E]'s A#2 comb"""
    xs = [math.log(REF_HZ)] + [math.log(hz(k)) for k in (78, 88)]
    ys = [math.log(REF_L)] + [math.log(plain_length(k)) for k in (78, 88)]
    up = -float(np.polyfit(xs, ys, 1)[0])
    # a pickup at d from the end notches harmonic L/d: L = d x (notch / f0)
    l_a2s = centre_m(46) * (A2S_NOTCH_HZ / A2S_HZ)
    down = math.log(l_a2s / REF_L) / math.log(REF_HZ / A2S_HZ)
    return up, down, l_a2s


def main(argv):
    up, down, l2 = length_law()
    print("STIFFNESS [E] Table 1, interpolated:", " ".join("%d:%.1e" % (k, B_at(k)) for k in (29, 41, 53, 65, 77, 88)))
    print("LENGTH: plain F#5 %.3f m, E6 %.3f m (B, .008\"); A#2 %.3f m ([E] Fig. 3's comb); "
          "law f^-%.3f over 161 Hz, f^-%.3f under" % (plain_length(78), plain_length(88), l2, up, down))
    print("RING [I], dB/s, h1..h6:")
    for k in (29, 41, 46, 53, 64, 70, 78, 88):
        print("  %2d %7.1f Hz  %s" % (k, hz(k), " ".join("%6.1f" % ring_dbs(k, n) for n in range(1, 7))))
    if argv[:1] == ["decay"]:
        fit_decay(dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a))
    elif argv[:1] == ["register"]:
        fit_register(dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a))
    elif argv[:1] == ["keyup"]:
        fit_keyup({a.split("=")[0]: 1 for a in argv if a.startswith("--")})
    elif argv[:1] == ["measure"]:
        measure()


KEYS = (29, 36, 41, 46, 53, 58, 64, 70, 76, 82, 88)


def _rate_err(cls, keys=KEYS, n=4):
    import upright_fit as U
    import wurli_fit as W
    E, rows = [], []
    for k in keys:
        y, sr = U.render(7, k, 100, 3.0)
        od = W.decays(y, sr, k, n=n)
        tg = [ring_dbs(k, m) for m in range(1, n + 1)]
        rows.append((k, od, tg))
        for m, (a, b) in enumerate(zip(tg, od)):
            if np.isfinite(b) and b > 0.3:
                # h1 THREE times: the fundamental is what is heard as the
                # sustain (Ben, on the first fit: "the sustain might need to
                # be a bit more")
                E += [np.log(b / a)] * (3 if m == 0 else 1)
    return float(np.sqrt(np.mean(np.square(E)))), rows


LADDER_H21, LADDER_H32 = 4.5, 0.0


def _ladder_err(keys=KEYS):
    """[E]'s ladder as a check: each key's h2 - h1 and h3 - h2"""
    import upright_fit as U
    import wurli_fit as W
    E, rows = [], []
    for k in keys:
        y, sr = U.render(7, k, 100, 0.6)
        lad = W.ladder(y, sr, k, n=4)
        h21, h32 = lad[1] - lad[0], lad[2] - lad[1]
        rows.append((k, h21, h32))
        E += [h21 - LADDER_H21, h32 - LADDER_H32]
    return float(np.sqrt(np.mean(np.square(E)))), rows


# THE REGISTER'S LEVEL: nothing published. Voiced even, as the other
# electric pianos are (a player's instrument is regulated so; OldBassMan's
# 200A holds within ~3 dB D2-D6): octave_gain so each key's loudest 100 ms at
# velocity 100 sits level, F1 to E6. (The Aalto fit's line through B-flat2 to
# F#5 had left F1 ~19 dB over C4.)
def fit_register(opts):
    import tonelib as T
    import dulcimer_fit as D
    import upright_fit as U
    import wurli_fit as W
    os.environ["TUNING_CABINET"] = "0"
    cls = T.ClavinetProperties

    def err():
        v = np.array([W.level(*U.render(7, k, 100, 0.6)) for k in KEYS])
        return float(np.sqrt(np.mean((v - v.mean()) ** 2)))
    D.nelder(cls, ["octave_gain"], err, {"octave_gain": 2.0}, int(opts.get("--maxfev", 30)), "level rms")


# THE KEY LETTING GO: [I] p.252 / [E] p.3, "the pitch decrease after release
# is three semitones for the whole keyboard" -- the tangent leaves, and the
# whole string, 2^(3/12) its speaking length, sounds until the yarn has it --
# and [E] s3.5's knock, "most of its energy concentrated below 1,200 Hz". So
# the key-up's string burst at its 2nd-4th harmonics three semitones down,
# and the mechanism's thump at three modes spread through the knock's band
# (150, 380, 950 Hz: an assumption, log-spaced), each mode alike (their
# shape is not published). Its level re the strike's first 50 ms is not
# published either: release_click_db -50, the quietest the renderer allows
# (blockrender._note_release_click drops a mode under 3e-3 of the note's gain,
# -50.5 dB) -- the key-up 26 dB under the strike. For Ben's ear to raise.
KEYUP_DB = -26.0
RELEASE_DROP = 2 ** (-3 / 12.0)


def keyup_level(cls, keys=(46, 64, 78)):
    """the key-up's loudest 50 ms re the strike's first 50 ms, dB, mean over keys"""
    import mido
    import blockrender as B
    import upright_fit as U

    def render(k):
        # held 1 s, then let go, and 0.5 s after it (U.render stops at the release)
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack(); m.tracks.append(t)
        t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
        t.append(mido.Message("program_change", channel=0, program=7, time=0))
        t.append(mido.Message("note_on", channel=0, note=k, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=k, velocity=0, time=960))
        t.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=480))
        L, R = B.render(m)[:2]
        return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR
    out = []
    keep = cls.release_click_db
    for k in keys:
        # THE KEY-UP ITSELF: the render with it less the render without it
        y, sr = render(k)
        cls.release_click_db = -200.0
        y0, _ = render(k)
        cls.release_click_db = keep
        d = y - y0
        t0 = U.onset(y, sr)
        n = int(0.05 * sr)
        strike = np.sqrt(np.mean(y[t0:t0 + n] ** 2))
        burst = max(np.sqrt(np.mean(d[i:i + n] ** 2)) for i in range(0, len(d) - n, n // 4))
        out.append(20 * np.log10(burst / strike + 1e-12))
    return float(np.mean(out)), out


def fit_keyup(opts):
    """the key-up's level, measured (the renderer's floor sets how low it may go)"""
    import tonelib as T
    os.environ["TUNING_CABINET"] = "0"
    lv, per = keyup_level(T.ClavinetProperties)
    print("  key-up %+.1f dB re the strike (keys %s); release_click_db %.1f" % (
        lv, " ".join("%+.1f" % v for v in per), T.ClavinetProperties.release_click_db))


def fit_decay(opts):
    import tonelib as T
    import dulcimer_fit as D
    os.environ["TUNING_CABINET"] = "0"
    cls = T.ClavinetProperties
    names = opts.get("--params", "decay_db,harmonic_decay_db,decay_register_slope").split(",")
    D.nelder(cls, names, lambda: _rate_err(cls)[0],
             {"decay_db": 0.3, "harmonic_decay_db": 1.0, "decay_register_slope": 0.15,
              "harmonic_decay_dampening": 0.1},
             int(opts.get("--maxfev", 40)), "log-rate rms")


def measure():
    import tonelib as T
    os.environ["TUNING_CABINET"] = "0"
    e, rows = _rate_err(T.ClavinetProperties)
    print("\n  OURS against the loss filter, h1..h4 dB/s (ours / target): log-rate rms %.2f" % e)
    for k, od, tg in rows:
        print("  %2d  %s" % (k, " ".join("%6.1f/%-6.1f" % (a, b) for a, b in zip(od, tg))))
    e, rows = _ladder_err()
    print("\n  LADDER, dB (target h2-h1 > +3, ~%+.1f; h3-h2 ~%+.1f): rms %.1f" % (LADDER_H21, LADDER_H32, e))
    for k, a, b in rows:
        print("  %2d  h2-h1 %+5.1f  h3-h2 %+5.1f" % (k, a, b))


if __name__ == "__main__":
    main(sys.argv[1:])
