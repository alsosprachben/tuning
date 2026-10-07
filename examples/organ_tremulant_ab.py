#!/usr/bin/env python3
"""The Tremulant, by ear: BWV 659 with and without it on the solo's division.

    python3 examples/organ_tremulant_ab.py [SCORE.mid] [SECONDS] [outdir]

Nun komm, der Heiden Heiland (BWV 659) is the tremulant's piece: an ornamented
cantus on a solo division over a soft accompaniment. The score (default
~/Downloads/midi/bwv659.mid: tracks Cantus Firmus, Accomp 8, Accomp 4, Ped 16,
Ped 8) is registered here as a console would have it, one channel a division,
the renderer stacking the ranks from the stop word (CC11 | CC43 << 7):

  solo       the cantus     flute 8 + octave 4   (+ the Tremulant, bit 13)
  accomp     Accomp 8       flute 8              (Accomp 4 was an octave
                                                  doubling standing in for a 4')
  pedal      Ped 8          bourdon 16 + flute 8 (Ped 16 likewise)

and rendered through examples/organ.py's recipe twice, TUNING_WIND=1 in both
so that only the stop differs, as MP3s at one common gain. Default 75 s into
~/Downloads/organ_wind.
"""
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

FLUTE8, OCTAVE4, BOURDON16, TREMULANT = 1 << 6, 1 << 1, 1 << 12, 1 << 13
PARTS = {"Cantus Firmus": (0, FLUTE8 | OCTAVE4), "Accomp 8": (1, FLUTE8), "Ped 8": (2, BOURDON16 | FLUTE8)}


def register(src, dst, trem, parts=None):
    m = mido.MidiFile(src)
    out = mido.MidiFile(type=1, ticks_per_beat=m.ticks_per_beat)
    for tr in m.tracks:
        name = next((e.name for e in tr if e.type == "track_name"), "")
        if not any(e.type == "note_on" for e in tr):
            out.tracks.append(tr.copy())             # the conductor: tempo, meter
            continue
        parts_ = parts or PARTS
        if name not in parts_:
            continue
        ch, word = parts_[name]
        if trem and ch == 0:
            word |= TREMULANT
        t = mido.MidiTrack()
        t.append(mido.MetaMessage("track_name", name=name, time=0))
        t.append(mido.Message("program_change", channel=ch, program=19, time=0))
        t.append(mido.Message("control_change", channel=ch, control=11, value=word & 0x7F, time=0))
        t.append(mido.Message("control_change", channel=ch, control=43, value=word >> 7, time=0))
        dt = 0
        for e in tr:
            dt += e.time
            if e.type in ("note_on", "note_off"):
                t.append(e.copy(channel=ch, time=dt))
                dt = 0
        out.tracks.append(t)
    out.save(dst)


def main(argv):
    from bitident import excerpt
    score = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/midi/bwv659.mid")
    secs = float(argv[2]) if len(argv) > 2 else 75.0
    out = argv[3] if len(argv) > 3 else os.path.expanduser("~/Downloads/organ_wind")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="organtrem_")
    wavs = {}
    for trem in (False, True):
        reg = os.path.join(d, "bwv659_%s.mid" % ("trem" if trem else "plain"))
        register(score, reg, trem)
        mid = reg[:-4] + "_%ds.mid" % secs
        excerpt(reg, secs).save(mid)
        od = os.path.join(d, "trem" if trem else "plain")
        env = dict(os.environ, TUNING_WIND="1")
        subprocess.run([sys.executable, os.path.join(HERE, "examples", "organ.py"), mid, od],
                       env=env, check=True, stdout=subprocess.DEVNULL)
        got = [f for f in os.listdir(od) if f.endswith(".wav") and "dry" not in f and "send" not in f]
        wavs[trem] = os.path.join(od, sorted(got, key=len)[-1])
    peak = 0.0
    for p in wavs.values():
        s = subprocess.run(["sox", p, "-n", "stat"], capture_output=True, text=True).stderr
        for k in ("Maximum amplitude", "Minimum amplitude"):
            peak = max(peak, abs(float([l for l in s.splitlines() if l.startswith(k)][0].split()[-1])))
    gain = -1.0 - 20 * np.log10(peak)
    for trem, p in wavs.items():
        mp3 = os.path.join(out, "bwv659_%s.mp3" % ("2_tremulant" if trem else "1_no_tremulant"))
        tmp = os.path.join(d, "g.wav")
        subprocess.run(["sox", p, "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
        subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
        print("  -> %s" % mp3)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
