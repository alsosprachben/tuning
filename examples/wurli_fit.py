#!/usr/bin/env python3
"""Measure GM 5's Wurlitzer against Chester Gwazda's 200A (Pianobook
"BaltiWurli", measured only; sources.md), and our render the same way.

    python3 examples/wurli_fit.py measure
    python3 examples/wurli_fit.py decay [--params=a,b] [--maxfev=N]
    python3 examples/wurli_fit.py pickup [--params=a,b] [--maxfev=N]
    python3 examples/wurli_fit.py action [--passes=N]   (writes tonelib.py)
    python3 examples/wurli_fit.py ab OUT.wav [--note-s=2.5]   DI, then ours (no cabinet), note by note
    python3 examples/wurli_fit.py abspk OUT.wav [--note-s=2.5]   the instrument as mixed, then ours

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

REFS = os.path.expanduser("~/Documents/refs/wurli/balti_ds/Balti Wurli  (DS)/Samples")
PROGRAM = 5
VEL = {"P": 35, "MF": 92, "F": 121}
PC = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def key_of(label):
    return (int(label[-1]) + 3) * 12 + PC[label[:-1]]


def recordings():
    """{(dyn, key): path} for the DI set."""
    out = {}
    for p in glob.glob(os.path.join(REFS, "BaltiWurli_DI_*.wav")):
        _, _, dyn, lab = os.path.basename(p)[:-4].split("_")
        out[(dyn, key_of(lab))] = p
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
    print("\n  LADDER h2..h8, dB re h1 (recorded / ours)")
    for (dyn, k), r in sorted(rows.items(), key=lambda q: (q[0][1], "PMF".index(q[0][0][0]))):
        print("  %3d %-2s %s" % (k, dyn, " ".join("%4.0f/%-4.0f" % (a, b) for a, b in zip(r["rl"][1:8], r["ol"][1:8]))))
    print("\n  DECAY h1..h6, dB/s (recorded / ours), MF")
    for (dyn, k), r in sorted(rows.items()):
        if dyn == "MF":
            print("  %3d    %s" % (k, " ".join("%5.1f/%-5.1f" % (a, b) for a, b in zip(r["rd"], r["od"]))))
    print("\n  LEVEL re MF, dB (recorded / ours)")
    for k in keys:
        if ("MF", k) not in rows:
            continue
        s = []
        for dyn in ("P", "F"):
            if (dyn, k) in rows:
                s.append("%s %+5.1f/%+5.1f" % (dyn, rows[(dyn, k)]["rv"] - rows[("MF", k)]["rv"],
                                                rows[(dyn, k)]["ov"] - rows[("MF", k)]["ov"]))
        print("  %3d  %s" % (k, "   ".join(s)))
    return rows


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
            if dyn == "P":
                continue
            y, sr = U.render(PROGRAM, k, VEL[dyn], 3.0)
            od = decays(y, sr, k)
            for a, b in zip(rd[:3], od[:3]):
                if np.isfinite(a) and np.isfinite(b) and a > 0.5 and b > 0.5 and a < 100:
                    E.append(np.log(b / a))
        return float(np.sqrt(np.mean(np.square(E))))
    D.nelder(cls, names, err, {"harmonic_decay_db": 3.0, "decay_register_slope": 0.2},
             int(opts.get("--maxfev", 40)), "log-rate rms")


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
            for r_, o_ in ((rl, ladder(y, sr, k, n=PICK_N)),
                           (rll, ladder(y, sr, k, n=PICK_N, a=LATE[0], b=LATE[1]))):
                a, b = np.maximum(r_[1:], -70), np.maximum(o_[1:], -70)
                ok = np.isfinite(a) & np.isfinite(b)
                E += list((b - a)[ok])
        return float(np.sqrt(np.mean(np.square(E))))
    D.nelder(cls, names, err, {"pickup_offset": 0.2, "pickup_deflection": 0.2,
                               "pickup_deflection_max": 0.3, "deflection_register_slope": 0.15,
                               "pickup_slot_q": 0.3, "pickup_slot_p": 1.0},
             int(opts.get("--maxfev", 80)), "ladder rms")


# THE ACTION (`action`): the hammer, the key and the damper, heard inside the
# case (the Mech set, an XY pair in it). Its takes are mostly the reeds'
# own acoustic sound -- 91-100% of 0.1-0.4 s at the note's partials -- and
# what is not is a thump in the first 50 ms, 60 Hz to ~2 kHz, strongest at
# 240-480, 25-30 dB down by 0.1 s, the same under every note. Fitted as
# strike_noise_db (the grand's strike machinery), against the speaker as it
# is heard: each set was recorded at its own gain, so the balance is the
# pack's own mix (BaltiWurli.dspreset: the Mechanical group -11.6 dB, the
# Speaker -1.4) -- the author's ear, not a measurement. Ours with the
# cabinet in, the thump read the same way: the energy between the note's
# partials in third octaves, 0-50 ms, re the speaker take's (ours': the
# render's) whole 0-50 ms.
MECH_DB, SPKR_DB = -11.580, -1.409


def _between(x, sr, k, a=0.0, b=0.05):
    t0 = U.onset(x, sr)
    n = 1 << 15
    seg = x[t0 + int(a * sr):t0 + int(b * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / sr)
    near = np.zeros_like(f, bool)
    f0 = hz(k)
    for m in range(1, 80):
        near |= np.abs(f - m * f0) < max(0.03 * m * f0, 8.0)
    out = []
    for lo, hi in zip(U.S3[:-1], U.S3[1:]):
        w = (f >= lo) & (f < hi)
        m_ = w & ~near
        out.append(X[m_].mean() * w.sum() if m_.any() else np.nan)
    return np.array(out), X.sum()


def action_targets():
    """{key: target dB a band}: the Mech take's thump, mixed under the
    speaker take of the same (or the nearest) key at MF."""
    spk = {}
    for p in glob.glob(os.path.join(REFS, "BaltiWurli_Spkr_MF_*.wav")):
        spk[key_of(os.path.basename(p)[:-4].split("_")[-1])] = p
    out = {}
    for p in glob.glob(os.path.join(REFS, "BaltiWurli_Mech_*.wav")):
        k = key_of(os.path.basename(p)[:-4].split("_")[-1])
        ks = min(spk, key=lambda q: abs(q - k))
        mb, _ = _between(*U.load(p), k)
        xs, sr = U.load(spk[ks])
        _, stot = _between(xs, sr, ks)
        out[k] = 10 * np.log10(mb + 1e-30) + MECH_DB - SPKR_DB - 10 * np.log10(stot)
    return out


def fit_action(opts):
    import re
    import tonelib as T
    cls = T.WurlitzerProperties
    os.environ["TUNING_CABINET"] = "1"
    tgt = action_targets()
    keys = sorted(tgt)
    if not getattr(cls, "strike_noise_db", ()):
        cls.strike_noise_db = tuple((int(round(c)), -40.0) for c in U.S3C)
    for it in range(int(opts.get("--passes", 4)) + 1):
        D = []
        for k in keys:
            y, sr = U.render(PROGRAM, k, VEL["MF"], 1.0)
            ob, otot = _between(y, sr, k)
            D.append(tgt[k] - (10 * np.log10(ob + 1e-30) - 10 * np.log10(otot)))
        D = np.array(D)
        ok = np.isfinite(D) & (np.array([tgt[k] for k in keys]) > -80)
        e = float(np.sqrt(np.mean(D[ok] ** 2)))
        print("  pass %d: action rec - ours, rms %.1f dB" % (it, e), flush=True)
        if it == int(opts.get("--passes", 4)):
            break
        band = np.array([np.nanmean(np.where(ok[:, j], D[:, j], np.nan)) if ok[:, j].any() else 0.0
                         for j in range(D.shape[1])])
        band = np.nan_to_num(band)
        old = dict(cls.strike_noise_db)
        cls.strike_noise_db = tuple((int(round(c)), round(float(np.interp(np.log(c), np.log(list(old)),
                                                                          list(old.values()))
                                                               + np.clip(0.8 * b, -15, 15)), 1))
                                    for c, b in zip(U.S3C, band))
    src = open(os.path.join(os.path.dirname(HERE), "tonelib.py")).read()
    a = src.index("class WurlitzerProperties(")
    body = src[a:]
    line = "    strike_noise_db = %s\n" % (cls.strike_noise_db,)
    body2 = re.sub(r"^    strike_noise_db = .*\n", lambda _: line, body, count=1, flags=re.M)
    open(os.path.join(os.path.dirname(HERE), "tonelib.py"), "w").write(src[:a] + body2)
    print(line)


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
        for dyn in ("P", "MF", "F"):
            if (dyn, k) not in rs:
                continue
            y, sr = U.render(PROGRAM, k, VEL[dyn], note_s + 0.5)
            parts += [A.fit_note(*U.load(rs[(dyn, k)])), gap, A.fit_note(y, sr), rest]
    x = np.concatenate(parts)
    write_wav(out, np.stack([x, x], 1), A.SR)


def abspk(out, note_s):
    """The whole instrument: each Speaker take (P, MF) with the Mech take of
    the same or the nearest key under it at the pack's own mix (Speaker -1.4,
    Mechanical -11.6 dB; onsets aligned), then ours with the cabinet in and
    the action, at the layer's velocity. Each pair peak-normalised alike."""
    import harpsi_ab as A
    from roomtail import write_wav
    from scipy.signal import resample_poly
    os.environ["TUNING_CABINET"] = "1"
    A.NOTE_S = note_s
    spk, mech = {}, {}
    for p in glob.glob(os.path.join(REFS, "BaltiWurli_Spkr_*.wav")):
        _, _, dyn, lab = os.path.basename(p)[:-4].split("_")
        if dyn in ("P", "MF"):
            spk[(dyn, key_of(lab))] = p
    for p in glob.glob(os.path.join(REFS, "BaltiWurli_Mech_*.wav")):
        mech[key_of(os.path.basename(p)[:-4].split("_")[-1])] = p

    def aligned(p):
        x, sr = U.load(p)
        if sr != A.SR:
            x = resample_poly(x, A.SR, sr)
        return x[max(0, U.onset(x, A.SR) - int(0.01 * A.SR)):]
    gap, rest = np.zeros(int(A.GAP_S * A.SR)), np.zeros(int(0.6 * A.SR))
    parts = []
    for k in sorted({k for _, k in spk}):
        for dyn in ("P", "MF"):
            if (dyn, k) not in spk:
                continue
            s_ = aligned(spk[(dyn, k)]) * 10 ** (SPKR_DB / 20)
            m_ = aligned(mech[min(mech, key=lambda q: abs(q - k))]) * 10 ** (MECH_DB / 20)
            n = max(len(s_), len(m_))
            x = np.pad(s_, (0, n - len(s_))) + np.pad(m_, (0, n - len(m_)))
            y, sr = U.render(PROGRAM, k, VEL[dyn], note_s + 0.5)
            parts += [A.fit_note(x, A.SR), gap, A.fit_note(y, sr), rest]
    x = np.concatenate(parts)
    write_wav(out, np.stack([x, x], 1), A.SR)


def main(argv):
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if argv[:1] == ["measure"]:
        measure_all()
    elif argv[:1] == ["decay"]:
        fit_decay(opts)
    elif argv[:1] == ["pickup"]:
        fit_pickup(opts)
    elif argv[:1] == ["action"]:
        fit_action(opts)
    elif argv[:1] == ["abspk"]:
        abspk(argv[1], float(opts.get("--note-s", 2.5)))
    elif argv[:1] == ["ab"]:
        ab(argv[1], float(opts.get("--note-s", 2.5)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
