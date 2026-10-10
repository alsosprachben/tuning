#!/usr/bin/env python3
"""Does a plucked or struck voice START as its recordings do?

    python3 examples/attack_audit.py [NAME ...] [--scan]

The bank's plucked and mallet voices began every partial at full level on
their first sample (an instant attack), and that edge clicked: in Neptune the
harp and celesta did it some four thousand times (Ben). Two numbers catch it,
per note, recording against ours:

  contrast  the top (above max(2 kHz, 8 f0)) in the first 3 ms against 5-15
            ms, dB: a click is a top that falls away at once
  early     that top in the first 3 ms against the whole note's first 50 ms

--scan renders each at a few onset times (attack_time) and prints the error
of each, so the class can take the one its recordings call for. SOURCES maps
each voice to its references: single-note files (note name in the name), or
Iowa's chromatic runs (one file, its notes in order), split at their onsets.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

REFS = os.path.expanduser("~/Documents/refs")
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# name: (program, velocity, ("single", glob) | ("run", file, first MIDI note, count))
SOURCES = {
    "harp":       (46, 80, [("single", "harp/raw/KSHarp_*_mf.wav")]),
    # VCSL's Steinway B, no pedal, the middle layer (normalized: levels say nothing)
    "grand":      (0, 80, [("single", "vcsl/steinway/JHPiano_NoSus_Close_*_vl3_rr1.wav")]),
    "crotales":   (112, 120, [("single", "cr_*.ff.aiff")]),
    "pizz_bass":  (32, 80, [("single", "pizz/bass/*.sul?.wav")]),
    "xylophone":  (13, 80, [("run", "xylophone_C5B5.wav", 72, 12)]),
    "marimba":    (12, 80, [("run", "marimba_C4B4.wav", 60, 12)]),
    "vibraphone": (11, 80, [("run", "vibraphone_C4B4.wav", 60, 12)]),
    "guitar":     (24, 80, [("run", "gtr_sulE.E2B2.aiff", 40, 8), ("run", "gtr_sulA.A2B2.aiff", 45, 3),
                            ("run", "gtr_sulD.D3B3.aiff", 50, 10), ("run", "gtr_sulG.G3B3.aiff", 55, 5),
                            ("run", "gtr_sulB.C4B4.aiff", 60, 12)]),
}


def note_of(name):
    m = re.search(r"(?:^|[_.\-])([A-G])([#b]?)(\d)(?:[_.\-]|$)", name)
    if not m:
        return None
    k = (int(m.group(3)) + 1) * 12 + NOTE[m.group(1)]
    return k + (1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0)


def mono(path):
    """A file as mono float, AIFF through sox (the WAV reader takes no AIFF)."""
    from drum_fit import read
    if path.lower().endswith((".aif", ".aiff")):
        import subprocess
        import tempfile
        tmp = tempfile.mktemp(suffix=".wav")
        subprocess.run(["sox", path, "-b", "16", tmp], check=True)
        try:
            a, sr = read(tmp)
        finally:
            os.remove(tmp)
    else:
        a, sr = read(path)
    a = a.astype(np.float64)
    return (a.mean(axis=1) if a.ndim > 1 else a), sr


def onset(x, thresh=1e-2):
    i = int(np.flatnonzero(np.abs(x) > thresh * np.abs(x).max())[0])
    return max(0, i - 44)


def measure(x, sr, t0, f0):
    from scipy.signal import butter, sosfiltfilt
    hc = min(18000.0, max(2000.0, 8 * f0))
    h = sosfiltfilt(butter(4, hc, btype="high", fs=sr, output="sos"), x)
    a = np.mean(h[t0:t0 + int(0.003 * sr)] ** 2)
    b = np.mean(h[t0 + int(0.005 * sr):t0 + int(0.015 * sr)] ** 2) + 1e-30
    c = np.mean(x[t0:t0 + int(0.05 * sr)] ** 2) + 1e-30
    return 10 * np.log10(a / b + 1e-30), 10 * np.log10(a / c + 1e-30)


def split_run(x, sr, count):
    """The onsets of a run: 5 ms energy rising 15 dB, within 35 dB of the
    file's peak, at least 0.3 s apart -- the first `count` of them."""
    n = int(0.005 * sr)
    e = np.array([np.mean(x[i:i + n] ** 2) for i in range(0, len(x) - n, n)])
    d = 10 * np.log10(e / e.max() + 1e-12)
    ons = []
    for i in range(1, len(d)):
        if d[i] > -35 and d[i] - d[i - 1] > 15 and (not ons or i * n - ons[-1] > 0.3 * sr):
            ons.append(i * n)
    return ons[:count]


def references(name):
    """[(MIDI note, contrast, early)] from the voice's recordings."""
    out = []
    for src in SOURCES[name][2]:
        if src[0] == "single":
            for p in sorted(glob.glob(os.path.join(REFS, src[1]))):
                k = note_of(os.path.basename(p))
                if k is None:
                    continue
                x, sr = mono(p)
                out.append((k,) + measure(x, sr, onset(x), 440 * 2 ** ((k - 69) / 12.0)))
        else:
            _, f, k0, count = src
            p = os.path.join(REFS, f)
            if not os.path.exists(p):
                continue
            x, sr = mono(p)
            for j, o in enumerate(split_run(x, sr, count)):
                seg = x[max(0, o - sr // 10):o + sr]
                out.append((k0 + j,) + measure(seg, sr, onset(seg), 440 * 2 ** ((k0 + j - 69) / 12.0)))
    return out


def render(prog, key, vel):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=96000)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=1000000, time=0))
    t.append(mido.Message("program_change", channel=0, program=prog, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=vel, time=int(0.5 * 96000) + 37))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=96000))
    L, R = B.render(m)[:2]
    y = np.asarray(L, np.float64) + np.asarray(R, np.float64)
    return measure(y, B.SR, onset(y, 1e-3), 440 * 2 ** ((key - 69) / 12.0))


def audit(name, scan):
    import patch_map
    prog, vel, _ = SOURCES[name]
    refs = references(name)
    if not refs:
        print("== %s: no references found" % name)
        return
    sub = refs[::max(1, len(refs) // 8)][:8]
    cls = {patch_map.property_class_for_note(prog, k) for k, _, _ in sub}
    rc, re_ = np.mean([r[1] for r in refs]), np.mean([r[2] for r in refs])
    print("== %s (GM %d, %d recorded notes; %s): recorded contrast %.1f, early %.1f"
          % (name, prog, len(refs), ", ".join(sorted(c.__name__ for c in cls)), rc, re_))
    opts = [None] + ([0.0005, 0.001, 0.002, 0.003, 0.005] if scan else [])
    for at in opts:
        keep = {c: c.__dict__.get("attack_time", "-") for c in cls}
        if at is not None:
            for c in cls:
                c.attack_time = at
        o = [render(prog, k, vel) for k, _, _ in sub]
        dc = np.array([a[0] - r[1] for a, r in zip(o, sub)])
        de = np.array([a[1] - r[2] for a, r in zip(o, sub)])
        print("   %-12s contrast %6.1f (err %5.1f)  early %6.1f (err %5.1f)  score %5.1f"
              % ("as is" if at is None else "%.4f s" % at, np.mean([a[0] for a in o]),
                 np.sqrt(np.mean(dc ** 2)), np.mean([a[1] for a in o]), np.sqrt(np.mean(de ** 2)),
                 np.sqrt((np.mean(dc ** 2) + np.mean(de ** 2)) / 2)), flush=True)
        for c, v in keep.items():
            if v == "-":
                if "attack_time" in c.__dict__:
                    delattr(c, "attack_time")
            else:
                c.attack_time = v


def main(argv):
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    names = [a for a in argv[1:] if not a.startswith("--")] or list(SOURCES)
    for n in names:
        audit(n, "--scan" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
