#!/usr/bin/env python3
"""The Electronic drum set (program 24 on the drum channel) against what the GM
sets play.

    python3 -I examples/elkit_fit.py            measure: each set's kit, then ours
    python3 -I examples/elkit_fit.py --fit=toms|kick|snare [--target=GeneralUser]
                                                fit ours to the sets' median, or
                                                to one set (tuned to its pitches)

LIKE THE ORCHESTRA HIT, A SAMPLED SET: Roland's Electronic set -- drum-machine
kick and snare, Simmons-style toms, a gated snare -- and the GM sets' own kits
are the instrument's lineage (FluidR3 and MuseScore General share theirs;
GeneralUser GS has its own; TimGM6mb builds its from synthetic waves).
Measured only. Each set's kit is rendered through TIMIDITY note by note, as
examples/sfx_levels.py renders the GM sets (every generator applied: the
transpositions, the envelopes), reverb and chorus off; ours through
blockrender, dry.

Per hit:
  PITCH    the strongest partial's track over the first 400 ms: its start,
           its end, how long it takes to fall halfway (a tom sweeps down)
  DECAY    the 5 ms level: peak, and when it is 10, 20, 40 dB down
  SPECTRUM energy in octave bands, 30 Hz-12 kHz, dB re the hit's total
  NOISE    the share between the spectrum's peaks (20th-percentile floor)
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

KIT = 24
NOTES = {36: "Elec BD", 38: "Elec SD", 40: "Gated SD", 41: "Elec Low Tom 2", 43: "Elec Low Tom 1",
         45: "Elec Mid Tom 2", 47: "Elec Mid Tom 1", 48: "Elec Hi Tom 2", 50: "Elec Hi Tom 1"}
OCT = 31.25 * 2 ** np.arange(0, 9)          # 31 Hz .. 8 kHz band centres
VEL = 100


def drum_mid(note, path, secs=2.0):
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=9, program=KIT, time=0))
    t.append(mido.Message("note_on", channel=9, note=note, velocity=VEL, time=240))
    t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=240))
    t.append(mido.MetaMessage("end_of_track", time=int(secs * 960)))
    m.save(path)


def read(path):
    from scipy.io import wavfile
    sr, x = wavfile.read(path)
    x = x.astype(float)
    x = x.mean(1) if x.ndim > 1 else x
    return x / 32768.0 if np.abs(x).max() > 2 else x, sr


def theirs(sf, note, d):
    cfg = os.path.join(d, "kit.cfg")
    with open(cfg, "w") as f:
        # the section is the KIT the file selects (program 24 on channel 10):
        # under "drumset 0" timidity fell back to the system config's FluidR3
        # kit for every set, and three sets measured identically
        f.write("drumset %d\n" % KIT)
        f.write('%d %%font "%s" 128 %d %d\n' % (note, sf, KIT, note))
    mid, wav = os.path.join(d, "t.mid"), os.path.join(d, "t.wav")
    drum_mid(note, mid)
    subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "44100",
                    "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return read(wav)


def ours(note, d):
    os.environ.setdefault("TUNING_REFLECT", "0")
    import blockrender as B
    mid = os.path.join(d, "o.mid")
    drum_mid(note, mid)
    L, R = B.render(mid)[:2]
    return 0.5 * (np.asarray(L, float) + np.asarray(R, float)), B.SR


def measure(x, sr):
    x = np.asarray(x, float)
    a = int(np.argmax(np.abs(x) > np.abs(x).max() * 0.02))
    x = x[a:]
    w = max(1, int(0.005 * sr))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) + 1e-12
    db = 20 * np.log10(e / e.max())
    p = int(np.argmax(db))
    times = []
    for lvl in (-10, -20, -40):
        k = np.flatnonzero(db[p:] < lvl)
        times.append((p + k[0]) / sr if len(k) else np.nan)
    # pitch: the strongest partial below 1.5 kHz, 20 ms frames, first 400 ms
    fr, hop = int(0.04 * sr), int(0.01 * sr)
    N = 1 << 15
    f = np.fft.rfftfreq(N, 1.0 / sr)
    band = (f > 25) & (f < 1500)
    track = []
    for i in range(p, min(len(x) - fr, p + int(0.4 * sr)), hop):
        X = np.abs(np.fft.rfft(x[i:i + fr] * np.hanning(fr), N))
        if db[i + fr // 2] < -35:
            break
        track.append(f[band][np.argmax(X[band])])
    track = np.array(track)
    if len(track) > 3:
        f0, f1 = float(np.median(track[:2])), float(np.median(track[-3:]))
        mid = f1 + 0.5 * (f0 - f1)
        k = np.flatnonzero(track <= mid) if f0 > f1 * 1.05 else []
        half = (k[0] * hop / sr) if len(k) else np.nan
    else:
        f0 = f1 = half = np.nan
    seg = x[p:p + int(0.25 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    tot = X[(f > 25) & (f < 12000)].sum()
    octs = [10 * np.log10(X[(f >= c / 2 ** 0.5) & (f < c * 2 ** 0.5)].sum() / tot + 1e-12) for c in OCT]
    lf = np.log2(np.maximum(f, 1.0))
    ok = (f > 40) & (f < min(12000, 0.45 * sr))
    floor = np.array([np.percentile(X[ok & (np.abs(lf - l) < 1 / 12.0)], 20) for l in lf[ok][::64]])
    noise = 10 * np.log10(floor.sum() * 64 / X[ok].sum() + 1e-12)
    return dict(f0=f0, f1=f1, half=half, times=times, octs=octs, noise=noise)


def show(label, m):
    print("   %-22s pitch %5.0f -> %5.0f Hz (half %s ms)  -10/-20/-40 dB at %s ms  noise %+4.0f dB"
          % (label, m["f0"], m["f1"], "%.0f" % (1000 * m["half"]) if np.isfinite(m["half"]) else "  -",
             "/".join("%.0f" % (1000 * t) if np.isfinite(t) else "-" for t in m["times"]), m["noise"]))
    print("   %-22s octaves 31-8k: %s" % ("", " ".join("%+4.0f" % v for v in m["octs"])))


# ---- the fit: ours toward the MEDIAN of the sets, feature by feature --------
# The three sets disagree (TimGM6mb's toms do not sweep at all; GeneralUser's
# fall over an octave), so no one of them is the target: each feature's median.
GROUPS = {
    "toms":  ("ElectronicTomProperties", (41, 45, 50)),
    "kick":  ("ElectronicKickProperties", (36,)),
    "snare": ("ElectronicSnareProperties", (38,)),
}
# the kit's tuning of these notes, x: the sets' median pitch over ours. The
# kick ends at 94, 51 and 47 Hz (ours 55); the snare starts at 133, 168 and
# 106 and ends at 149, 231 and 58 (ours 220): 140.
PITCH = {"kick": 51.0 / 55.0, "snare": 140.0 / 220.0}
NOISE_HZ = tuple(400.0 * 2 ** (k / 3.0) for k in range(15))   # 400 Hz - 10 kHz


def targets(sets, notes, d):
    """Per note: the sets' median of every feature."""
    out = {}
    for note in notes:
        ms = [measure(*theirs(sf, note, d)) for _n, sf in sets]
        r = [m["f0"] / m["f1"] if np.isfinite(m["f0"]) and m["f1"] > 0 else 1.0 for m in ms]
        hv = [m["half"] for m in ms if np.isfinite(m["half"])]
        out[note] = dict(ratio=float(np.median(r)), half=float(np.median(hv)) if hv else np.nan,
                         times=np.nanmedian([m["times"] for m in ms], 0),
                         octs=np.median([m["octs"] for m in ms], 0),
                         noise=float(np.median([m["noise"] for m in ms])),
                         # the pitch it settles to: the end of a fall, or the
                         # start where the tracker reads a rise (a snare's wires)
                         low=float(np.median([min(m["f0"], m["f1"]) for m in ms])))
    return out


def apply(cls_name, notes, x):
    """x = (sweep, log settle s, log decay scale, noise dB, noise dB/octave,
    log noise fall dB/s[, log pitch scale]), onto the class and the kit's
    rings and, with a seventh, the kit's tuning of these notes."""
    import tonelib as T
    import percussion_map as P
    c = getattr(T, cls_name)
    bend, settle, ring, lv, sl, fall = x[:6]
    if len(x) > 6:
        # a pitch scale: one for every note, or {note: scale}
        base_f = apply.freqs.setdefault(cls_name, {n: P.KITS[KIT][n] for n in notes})
        for n in notes:
            nm, cl, fq = base_f[n]
            k = x[6].get(n, 1.0) if isinstance(x[6], dict) else float(np.exp(x[6]))
            P.KITS[KIT][n] = (nm, cl, fq * k)
    c.tension_bend = max(0.0, float(bend))
    c.tension_bend_max = max(c.tension_bend, 0.0)
    c.tension_settle_time = float(np.exp(settle))
    # the STRIKE (blockrender: strike_noise_db, rows a third octave apart,
    # falling strike_noise_dbs) -- the layers are emitted only beside one
    c.strike_noise_db = tuple((round(hz), float(lv + sl * np.log2(hz / 1000.0))) for hz in NOISE_HZ)
    c.strike_noise_dbs = float(np.exp(fall))
    c.strike_noise_len_s = 1.0
    c.strike_noise_fade_s = 0.001
    base = apply.base.setdefault(cls_name, (dict(P.KIT_RING.get(KIT, {})), c.decay_db))
    for n in notes:
        if n in base[0]:
            P.KIT_RING[KIT][n] = base[0][n] * float(np.exp(ring))
    if not any(n in base[0] for n in notes):
        c.decay_db = base[1] / float(np.exp(ring))
    P._RING_CLASSES.clear()


apply.base = {}
apply.freqs = {}


def score(m, t):
    """dB-like distance: the spectrum (bands the sets hold above -50), the
    decay, the sweep's depth and time, the noise share."""
    o, w = np.maximum(m["octs"], -50.0), np.maximum(t["octs"], -50.0)
    band = float(np.sqrt(np.mean((o - w) ** 2)))
    tm = np.asarray(m["times"]), np.asarray(t["times"])
    ok = np.isfinite(tm[0]) & np.isfinite(tm[1])
    dec = float(np.mean(np.abs(10 * np.log2(tm[0][ok] / tm[1][ok])))) if ok.any() else 10.0
    r = m["f0"] / m["f1"] if np.isfinite(m["f0"]) and m["f1"] > 0 else 1.0
    sw = 24.0 * abs(np.log2(r / t["ratio"]))                 # 2 dB a semitone
    hf = 0.0
    if np.isfinite(t["half"]):
        hf = 5.0 * abs(np.log2((m["half"] if np.isfinite(m["half"]) else 400e-3) / (t["half"])))
    return band + dec + sw + hf + 0.3 * abs(m["noise"] - t["noise"])


def fit(group, sets, d, own=False):
    """own: the target is one set, and each note is tuned to ITS pitch."""
    from scipy.optimize import minimize
    import tonelib as T
    import percussion_map as P
    cls_name, notes = GROUPS[group]
    tg = targets(sets, notes, d)
    c = getattr(T, cls_name)
    # THE TUNING IS NOT FITTED: free, it traded an octave for one band (the
    # kick to 28 Hz for the 31 Hz octave; the snare UP, x1.29). It is the
    # sets' median pitch instead (PITCH), and six parameters fit around it.
    # The noise starts low: at -10 dB it swamped the kick, and the search
    # stayed there.
    # ...and a deep sweep to start from where the set has one: from the kick's
    # old 0.64 the search never left the small bend (55 -> 51 Hz against
    # GeneralUser's 129 -> 51)
    bend0 = max(c.tension_bend, (tg[notes[0]]["ratio"] - 1.0)) if own else c.tension_bend
    x0 = np.array([bend0, np.log(c.tension_settle_time), 0.0, -45.0, 0.0, np.log(40.0)])
    step = np.array([0.2, 0.5, 0.3, 8.0, 3.0, 0.7])
    tune = [np.log(PITCH[group])] if group in PITCH else []
    if own:
        tune = [{n: tg[n]["low"] / P.KITS[KIT][n][2] for n in notes}]
    seen = {}

    def f(x):
        apply(cls_name, notes, list(x) + tune)
        tot = sum(score(measure(*ours(n, d)), tg[n]) for n in notes) / len(notes)
        seen[tuple(np.round(x, 4))] = tot
        print("   %.2f  %s" % (tot, " ".join("%.3f" % v for v in x)), flush=True)
        return tot
    r = minimize(f, x0, method="Nelder-Mead",
                 options=dict(initial_simplex=np.vstack([x0] + [x0 + np.eye(len(x0))[i] * step[i]
                                                                 for i in range(len(x0))]),
                              maxfev=200, xatol=0.01, fatol=0.05))
    apply(cls_name, notes, list(r.x) + tune)
    bend, settle, ring, lv, sl, fall = r.x[:6]
    if own:
        print("   tuned to the set: %s" % ", ".join("%d %.1f Hz" % (n, tg[n]["low"]) for n in notes))
    elif tune:
        print("   pitch x%.3f (the sets' median, held)" % PITCH[group])
    print("FITTED %s  score %.2f (from %.2f)" % (group, r.fun, seen[tuple(np.round(x0, 4))]))
    print("   tension_bend %.3f  tension_settle_time %.4f  ring x%.3f  noise %+.1f dB at 1 kHz, %+.1f dB/oct, %.1f dB/s"
          % (bend, np.exp(settle), np.exp(ring), lv, sl, np.exp(fall)))
    for n in notes:
        print("== %d %s   (the sets' median: ratio %.2f, half %.0f ms, -10/-20/-40 %s ms, noise %+.0f)"
              % (n, NOTES[n], tg[n]["ratio"], 1000 * tg[n]["half"],
                 "/".join("%.0f" % (1000 * v) for v in tg[n]["times"]), tg[n]["noise"]))
        print("   %-22s octaves 31-8k: %s" % ("median", " ".join("%+4.0f" % v for v in tg[n]["octs"])))
        show("ours, fitted", measure(*ours(n, d)))
    return r.x


def main(argv):
    from gm_release import SETS
    sets = [(n, p) for n, p in SETS if p and os.path.exists(p) and not n.startswith("MuseScore")]
    grp = next((a.split("=", 1)[1] for a in argv if a.startswith("--fit=")), None)
    # --target=NAME: one set (a prefix of its name, e.g. GeneralUser) instead
    # of the median of all three
    tgt = next((a.split("=", 1)[1] for a in argv if a.startswith("--target=")), None)
    if tgt:
        sets = [(n, p) for n, p in sets if n.lower().startswith(tgt.lower())]
    with tempfile.TemporaryDirectory() as d:
        if grp:
            fit(grp, sets, d, own=bool(tgt))
            return 0
        for note, name in sorted(NOTES.items()):
            print("== %d %s" % (note, name), flush=True)
            for sname, sf in sets:
                show(sname.split()[0], measure(*theirs(sf, note, d)))
            show("ours", measure(*ours(note, d)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
