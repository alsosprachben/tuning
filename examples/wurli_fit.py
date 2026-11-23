#!/usr/bin/env python3
"""Measure GM 5's Wurlitzer against two openly licensed 200-series sets, and
our render the same way (since 2026-11-22; Gwazda's Pianobook BaltiWurli, the
first reference, is no longer read: licences.md L7):

  OldBassMan's "Wurlitzer 200a" (Freesound pack 5726, CC BY 4.0;
  ~/Documents/refs/wurli_oldbassman): 13 notes D2-D6 in thirds, one dynamic
  (taken as MF), 48 kHz/24-bit, "sampled thru a Lundal Transformer and a real
  Tube Preamp" -- the pickup's output, full band, 5-12 s, levels as played
  (peaks -5.6 to -7.9 dBFS). The file names sit an octave over what sounds
  (d3 is D2) and lost their sharps (a3 is A#2).
  Greg Sullivan's "Wurlitzer EP200" (his EP203W; CC BY 4.0, sullivang.net;
  ~/Documents/refs/epianos_sullivan/ep200_wav, decoded from the sfz set's
  flac): 11 keys A1-Ab6 at pp/mp/f/ff -- the only witness to how the tone
  grows with velocity. But BAND-LIMITED (nothing above ~4-6 kHz: a 1999
  sampler set), each take normalized to 0 dBFS, short and looped: its ladder
  is read under SULLIVAN_HZ and at the strike only, and it says nothing of
  levels or decay.

    python3 examples/wurli_fit.py measure
    python3 examples/wurli_fit.py decay [--params=a,b] [--maxfev=N]
    python3 examples/wurli_fit.py pickup [--params=a,b] [--maxfev=N]
    python3 examples/wurli_fit.py register [--maxfev=N]
    python3 examples/wurli_fit.py ab OUT.wav [--note-s=2.5]   DI, then ours (no cabinet), note by note
    (the action's knock: examples/wurli_action.py, modelled)

THE DI, NOT THE SPEAKER. The DI set is the pickup's own output -- the reed
through its 1/d plate and nothing after it -- which is exactly what
tonelib.WurlitzerProperties' pickup model makes; so ours is rendered with the
cabinet out (TUNING_CABINET=0) and no CC1 (no tremolo). Nine notes, C2-F#6,
at P / MF / F, played here at the middle of each layer's velocity range in
the set's own map (1-69, 70-115, 116-127). The file labels sit two octaves
under what sounds: key = (label octave + 3) * 12 + pitch class.

Per note and dynamic:
  ladder  harmonics 1-12, dB re h1, 30-230 ms after the onset (the bark)
  decay   harmonics 1-6, dB/s, a line through 20 ms levels from 0.1 s until
          30 dB down or 2 s -- the model says h_k decays at k times h1
  level   the loudest 100 ms, dB, re the MF note's (the dynamics' spread)
"""
import glob
import os
import sys

import numpy as np

os.environ.setdefault("TUNING_CABINET", "0")


def di_only():
    """Ours as the DI hears it: no cabinet (TUNING_CABINET=0) and no action --
    the thump is the room's, never in the pickup's signal."""
    import tonelib as T
    T.WurlitzerProperties.strike_noise_db = ()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

OBM = os.path.expanduser("~/Documents/refs/wurli_oldbassman")
SULLIVAN = os.path.expanduser("~/Documents/refs/epianos_sullivan/ep200_wav")
PROGRAM = 5
# OldBassMan's one dynamic as MF; Sullivan's layers at the middle of his own
# map's ranges (1-37, 38-65, 66-89, 90-127)
VEL = {"MF": 92, "pp": 19, "mp": 52, "f": 78, "ff": 109}
DYNS = ("pp", "mp", "MF", "f", "ff")
SULLIVAN_HZ = 3500.0
PC = {"c": 0, "db": 1, "d": 2, "eb": 3, "e": 4, "f": 5, "gb": 6, "g": 7, "ab": 8, "a": 9, "bb": 10, "b": 11}


def band(dyn):
    """the highest frequency a take of this layer holds"""
    return 1e9 if dyn == "MF" else SULLIVAN_HZ


def recordings():
    """{(dyn, key): path}: OldBassMan's as MF, Sullivan's as pp/mp/f/ff."""
    out = {}
    for p in glob.glob(os.path.join(OBM, "*__oldbassman__*.wav")):
        lab = os.path.basename(p)[:-4].split("__")[2]          # 'd3' is D2, 'a3' A#2
        out[("MF", int(lab[1]) * 12 + {"d": 2, "f": 6, "a": 10}[lab[0]])] = p
    for p in glob.glob(os.path.join(SULLIVAN, "*.wav")):
        b = os.path.basename(p)[:-4]
        name = b.rstrip("pfm")
        out[(b[len(name):], (int(name[-1]) + 1) * 12 + PC[name[:-1]])] = p
    return out


def hz(k):
    return 440.0 * 2 ** ((k - 69) / 12.0)


def ladder(x, sr, k, n=12, a=0.03, b=0.23):
    t0 = U.onset(x, sr)
    X, f = U.spectrum(x, sr, t0, a, b, 1 << 17)
    f0 = hz(k)
    out = []
    for m in range(1, n + 1):
        if m * f0 > 0.45 * sr:
            out.append(np.nan)
            continue
        w = (f > m * f0 * 0.97) & (f < m * f0 * 1.03)
        out.append(10 * np.log10(X[w].max() + 1e-30))
    out = np.array(out)
    return out - out[0]


def decays(x, sr, k, n=6):
    from scipy.signal import butter, sosfiltfilt
    t0 = U.onset(x, sr)
    f0 = hz(k)
    out = []
    w = int(0.02 * sr)
    for m in range(1, n + 1):
        fm = m * f0
        bw = max(6.0, 0.04 * fm)
        if fm + bw > 0.45 * sr:
            out.append(np.nan)
            continue
        y = sosfiltfilt(butter(2, [fm - bw, fm + bw], btype="band", fs=sr, output="sos"), x[t0:])
        e = 10 * np.log10(np.array([np.mean(y[i:i + w] ** 2) for i in range(0, len(y) - w, w)]) + 1e-30)
        a = int(0.1 / 0.02)
        pk = e[a]
        stop = min(len(e), int(2.0 / 0.02))
        below = np.flatnonzero(e[a:stop] < pk - 30)
        bb = a + (below[0] if len(below) else stop - a)
        if bb - a < 5:
            out.append(np.nan)
            continue
        t = np.arange(a, bb) * 0.02
        out.append(-float(np.polyfit(t, e[a:bb], 1)[0]))
    return np.array(out)


def level(x, sr):
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    n = int(0.1 * sr)
    return 10 * np.log10((c[n:] - c[:-n]).max() / n + 1e-30)


def measure_all():
    di_only()
    rs = recordings()
    keys = sorted({k for _, k in rs})
    print("  keys:", keys)
    rows = {}
    for (dyn, k), p in sorted(rs.items(), key=lambda q: (q[0][1], q[0][0])):
        x, sr = U.load(p)
        y, ysr = U.render(PROGRAM, k, VEL[dyn], 3.0)
        rows[(dyn, k)] = dict(rl=ladder(x, sr, k), ol=ladder(y, ysr, k), rd=decays(x, sr, k),
                              od=decays(y, ysr, k), rv=level(x, sr), ov=level(y, ysr))
    print("\n  LADDER h2..h8, dB re h1 (recorded / ours; '--' over the take's band)")
    for (dyn, k), r in sorted(rows.items(), key=lambda q: (q[0][1], DYNS.index(q[0][0]))):
        print("  %3d %-2s %s" % (k, dyn, " ".join(
            ("%4.0f/%-4.0f" % (a, b)) if (m + 2) * hz(k) < band(dyn) else "    --   "
            for m, (a, b) in enumerate(zip(r["rl"][1:8], r["ol"][1:8])))))
    print("\n  DECAY h1..h6, dB/s (recorded / ours), OldBassMan's (MF)")
    for (dyn, k), r in sorted(rows.items()):
        if dyn == "MF":
            print("  %3d    %s" % (k, " ".join("%5.1f/%-5.1f" % (a, b) for a, b in zip(r["rd"], r["od"]))))
    rv, ov = register_levels(rows)
    print("\n  REGISTER LEVEL, MF, dB re the notes' mean (recorded / ours): rms %.1f" % np.sqrt(np.mean((ov - rv) ** 2)))
    for k, a, b in zip(sorted(k for d, k in rows if d == "MF"), rv, ov):
        print("  %3d  %+5.1f/%+5.1f" % (k, a, b))
    return rows


def register_levels(rows):
    """OldBassMan's loudest 100 ms a note, and ours, each re its own mean"""
    ks = sorted(k for d, k in rows if d == "MF")
    rv = np.array([rows[("MF", k)]["rv"] for k in ks])
    ov = np.array([rows[("MF", k)]["ov"] for k in ks])
    return rv - rv.mean(), ov - ov.mean()


# THE LOUDEST TAKES ARE CLIPPED. Every F take below C7 sits on the same
# ceiling, 0.708 of full scale (-3.0 dBFS), for 60-176 samples between the
# strike and up to 1.2 s -- a clipper in the recording chain, and the
# "metallic, clipped edge" Ben heard on them before the fade. MF and P never
# touch it (one sample at their peak). Their harmonics are the clipper's, not
# the pickup's, so they are left out of every fit; the two clean F takes, C7
# and F#7, stay.
def clipped(x):
    pk = np.abs(x).max()
    return int((np.abs(x) >= 0.999 * pk).sum()) > 8


def _rec_cache():
    rs = recordings()
    rs = {dk: p for dk, p in rs.items() if not clipped(U.load(p)[0])}
    return {dk: (lambda xs: (ladder(*xs, dk[1], n=PICK_N), decays(*xs, dk[1]),
                             ladder(*xs, dk[1], n=PICK_N, a=LATE[0], b=LATE[1])))(U.load(p))
            for dk, p in rs.items()}


# THE DECAY (`decay`): the reed's own rate and how it climbs the keyboard
# (harmonic_decay_db, decay_register_slope), against h1-h3 at MF and F, as
# log rates. Measured, the k*D law holds -- the bass's h1..h6 at about 2, 4,
# 6, 8 dB/s -- but the reed's D climbs about an octave's doubling, ~2 dB/s at
# C2 to ~44 at F#6, where ours ran 14 to 57.
def fit_decay(opts):
    di_only()
    import tonelib as T
    import dulcimer_fit as D
    cls = T.WurlitzerProperties
    rec = _rec_cache()
    names = opts.get("--params", "harmonic_decay_db,decay_register_slope").split(",")

    def err():
        E = []
        for (dyn, k), (rl, rd, _) in rec.items():
            if dyn != "MF":              # Sullivan's: short and looped
                continue
            y, sr = U.render(PROGRAM, k, VEL[dyn], 3.0)
            od = decays(y, sr, k)
            for a, b in zip(rd[:3], od[:3]):
                if np.isfinite(a) and np.isfinite(b) and a > 0.5 and b > 0.5 and a < 100:
                    E.append(np.log(b / a))
        return float(np.sqrt(np.mean(np.square(E))))
    D.nelder(cls, names, err, {"harmonic_decay_db": 3.0, "decay_register_slope": 0.2},
             int(opts.get("--maxfev", 40)), "log-rate rms")


# THE REGISTER'S LEVEL (`register`): octave_gain against OldBassMan's levels,
# each note's loudest 100 ms re the notes' mean (his takes kept the levels he
# played them at), ours at MF with the cabinet out -- the pickup's output, as
# his chain took it.
def fit_register(opts):
    di_only()
    import tonelib as T
    import dulcimer_fit as D
    cls = T.WurlitzerProperties
    rs = {dk: p for dk, p in recordings().items() if dk[0] == "MF"}
    rec = {dk: level(*U.load(p)) for dk, p in rs.items()}

    def err():
        rows = {dk: dict(rv=rec[dk], ov=level(*U.render(PROGRAM, dk[1], VEL["MF"], 0.6))) for dk in rs}
        rv, ov = register_levels(rows)
        return float(np.sqrt(np.mean((ov - rv) ** 2)))
    D.nelder(cls, ["octave_gain"], err, {"octave_gain": 1.0}, int(opts.get("--maxfev", 30)), "level rms")


# THE PICKUP (`pickup`): the gap, the swing, how close to the plate it may
# come and how the swing grows down the keyboard, against every note's
# ladder h2-h8 at P, MF and F (dB re h1, both floored at -60: under that the
# takes have their noise).
PICKUP = "pickup_offset,pickup_deflection,pickup_deflection_max,deflection_register_slope,pickup_slot_q,pickup_slot_p"
# h2-h32, floored at -70: the bass's buzz lives far up its series (C2's h8-h32
# is 0.5-2 kHz), which h2-h8 never saw
PICK_N = 32
# ...AND LATE, 0.6-1.0 s, too: through a slot the bark collapses as the swing
# decays and the fundamental comes back (pickup_layers), which the strike's
# ladder alone does not see.
LATE = (0.6, 1.0)


def fit_pickup(opts):
    di_only()
    import tonelib as T
    import dulcimer_fit as D
    cls = T.WurlitzerProperties
    rec = _rec_cache()
    names = opts.get("--params", PICKUP).split(",")

    def err():
        T._EP_PICKUP_CACHE.clear()
        E = []
        for (dyn, k), (rl, rd, rll) in rec.items():
            y, sr = U.render(PROGRAM, k, VEL[dyn], 1.2)
            inband = (np.arange(2, PICK_N + 1) * hz(k)) < band(dyn)
            pairs = [(rl, ladder(y, sr, k, n=PICK_N))]
            if dyn == "MF":             # Sullivan's loop by then
                pairs.append((rll, ladder(y, sr, k, n=PICK_N, a=LATE[0], b=LATE[1])))
            for r_, o_ in pairs:
                a, b = np.maximum(r_[1:], -70), np.maximum(o_[1:], -70)
                ok = np.isfinite(a) & np.isfinite(b) & inband
                E += list((b - a)[ok])
        return float(np.sqrt(np.mean(np.square(E))))
    D.nelder(cls, names, err, {"pickup_offset": 0.2, "pickup_deflection": 0.2,
                               "deflection_velocity_power": 0.2,
                               "pickup_deflection_max": 0.3, "deflection_register_slope": 0.15,
                               "pickup_slot_q": 0.3, "pickup_slot_p": 1.0},
             int(opts.get("--maxfev", 80)), "ladder rms")


def ab(out, note_s):
    """Each recorded DI note, then ours at its dynamic's velocity with the
    cabinet out, then a rest -- P, MF, F a note at a time, low to high; each
    peak-normalised alike (harpsi_ab.fit_note), so it is colour and decay,
    the dynamics' levels apart."""
    di_only()
    import harpsi_ab as A
    from roomtail import write_wav
    A.NOTE_S = note_s
    rs = recordings()
    gap, rest = np.zeros(int(A.GAP_S * A.SR)), np.zeros(int(0.6 * A.SR))
    parts = []
    for k in sorted({k for _, k in rs}):
        for dyn in DYNS:
            if (dyn, k) not in rs:
                continue
            y, sr = U.render(PROGRAM, k, VEL[dyn], note_s + 0.5)
            parts += [A.fit_note(*U.load(rs[(dyn, k)])), gap, A.fit_note(y, sr), rest]
    x = np.concatenate(parts)
    write_wav(out, np.stack([x, x], 1), A.SR)


def main(argv):
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if argv[:1] == ["measure"]:
        measure_all()
    elif argv[:1] == ["decay"]:
        fit_decay(opts)
    elif argv[:1] == ["register"]:
        fit_register(opts)
    elif argv[:1] == ["pickup"]:
        fit_pickup(opts)
    elif argv[:1] == ["ab"]:
        ab(argv[1], float(opts.get("--note-s", 2.5)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
