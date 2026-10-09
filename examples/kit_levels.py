#!/usr/bin/env python3
"""The kit's balance against other GM implementations: each percussion note
struck alone, its level re the snare (38).

    python3 examples/kit_levels.py [--vel=100] [--notes=35,36,...] [SF2 ...]

Each SoundFont (default: FluidR3_GM from /usr/share/sounds/sf2, and
GeneralUser GS and MuseScore General from ~/Documents/refs/soundfonts --
sources.md) is played through timidity with its reverb and chorus off; ours
is rendered as examples/crash_fit.py renders a stroke (no reflections, master
-14 dB). Two readings a note, both the loudest 150 ms:

  rms  plain power, drumset_check's reading -- what the kit was levelled on
  K    K-weighted (ITU-R BS.1770: the head's high shelf, the low cut) --
       nearer what the ear calls loud; plain power counts a kick's 50 Hz at
       full weight

A SoundFont's balance is its maker's judgement of a kit as played, which is
the thing a close microphone cannot tell us (see tonelib.SideStickProperties).
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.signal import lfilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import mido  # noqa: E402

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402

DEFAULT_SF = ("/usr/share/sounds/sf2/FluidR3_GM.sf2",
              "~/Documents/refs/soundfonts/GeneralUser-GS.sf2",
              "~/Documents/refs/soundfonts/MuseScore_General.sf2")
NOTES = (35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54,
         55, 56, 57, 59, 60, 62, 63, 64, 69, 70, 75, 76, 81)


def kweight(x, sr):
    """BS.1770's two stages, designed for this rate (pyloudnorm's formulas)."""
    # high shelf, +4 dB from ~1.7 kHz
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    A = 10 ** (G / 40.0)
    w0 = 2 * np.pi * fc / sr
    al = np.sin(w0) / (2 * Q)
    b = [A * ((A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * al),
         -2 * A * ((A - 1) + (A + 1) * np.cos(w0)),
         A * ((A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * al,
         2 * ((A - 1) - (A + 1) * np.cos(w0)),
         (A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * al]
    x = lfilter(b, a, x)
    # the low cut, 38 Hz
    Q, fc = 0.5003270373238773, 38.13547087602444
    w0 = 2 * np.pi * fc / sr
    al = np.sin(w0) / (2 * Q)
    b = [(1 + np.cos(w0)) / 2, -(1 + np.cos(w0)), (1 + np.cos(w0)) / 2]
    a = [1 + al, -2 * np.cos(w0), 1 - al]
    return lfilter(b, a, x)


def levels(chs, sr):
    return C.level(chs, sr), C.level([kweight(c, sr) for c in chs], sr)


def stroke_mid(note, vel, path):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=120))
    t.append(mido.MetaMessage("end_of_track", time=2880))
    m.save(path)


def sf_levels(sf, notes, vel, d):
    cfg = os.path.join(d, "t.cfg")
    # timidity reads its system config first (Debian's maps FluidR3 note by
    # note) and -c only adds to it, so a bare `soundfont` line loses to those
    # mappings: every drum note is mapped to this font's kit explicitly
    with open(cfg, "w") as f:
        f.write("drumset 0\n")
        for n in range(27, 88):
            f.write('%d %%font "%s" 128 0 %d\n' % (n, sf, n))
    out = {}
    for n in notes:
        mid, wav = os.path.join(d, "n.mid"), os.path.join(d, "n.wav")
        stroke_mid(n, vel, mid)
        subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "44100",
                        "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        a, sr = read(wav)
        a = a.astype(np.float64)
        out[n] = levels([a[:, 0], a[:, 1]] if a.ndim > 1 else [a], sr) if np.abs(a).max() > 0 else None
    return out


def ours(notes, vel):
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import percussion_map as PM
    return {n: levels(*C.render(n, vel, 1.5)) if n in PM.PERCUSSION else None for n in notes}


def main(argv):
    vel = int(next((a.split("=")[1] for a in argv if a.startswith("--vel=")), 100))
    notes = next((tuple(int(x) for x in a.split("=")[1].split(",")) for a in argv
                  if a.startswith("--notes=")), NOTES)
    sfs = [a for a in argv[1:] if not a.startswith("--")] or [os.path.expanduser(s) for s in DEFAULT_SF]
    import percussion_map as PM
    cols = [("ours", ours(notes, vel))]
    with tempfile.TemporaryDirectory() as d:
        for sf in sfs:
            cols.append((os.path.basename(sf).split(".")[0][:14], sf_levels(sf, notes, vel, d)))
    for k, kind in ((0, "rms"), (1, "K")):
        print("\n== velocity %d, %s level re the snare (38), dB" % (vel, kind))
        print("  note %-18s" % "" + "".join("%15s" % c for c, _ in cols))
        for n in notes:
            row = []
            for _, lv in cols:
                v, r = lv.get(n), lv.get(38)
                row.append("%15s" % ("%+.1f" % (v[k] - r[k]) if v and r else "--"))
            name = PM.PERCUSSION[n][0] if n in PM.PERCUSSION else ""
            print("  %4d %-18s" % (n, name[:18]) + "".join(row))
    # ...and with no reference drum at all: each note's level in ours less the
    # fonts' mean, less the median of that over the kit. A snare that sits low
    # in ours shows here as the snare, not as everything else sitting high.
    for k, kind in ((0, "rms"), (1, "K")):
        dev = {}
        for n in notes:
            o = cols[0][1].get(n)
            f = [lv[n][k] for _, lv in cols[1:] if lv.get(n)]
            if o and f:
                dev[n] = (o[k] - np.mean(f), float(np.ptp(f)))
        med = float(np.median([d for d, _ in dev.values()]))
        print("\n== velocity %d, %s: ours against the fonts' mean, the kit's median offset (%.1f dB) taken out" % (vel, kind, med))
        for n, (d, sp) in sorted(dev.items(), key=lambda kv: -kv[1][0]):
            name = PM.PERCUSSION[n][0] if n in PM.PERCUSSION else ""
            print("  %4d %-18s %+6.1f   (fonts span %4.1f)" % (n, name[:18], d - med, sp))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
