#!/usr/bin/env python3
"""Our organ's pipes, measured as Pitea's were: does the wind land?

    python3 examples/organ_wind_check.py [WIND] [--keep DIR]

Renders single pipes of three of the console's ranks -- principal 8 (stop bit
0), flute 8 (bit 6), reed 8 (bit 8) -- at C3, C4, C5 and C6, held 3.5 s, dry
(TUNING_REFLECT=0: the source, as the measurement wants it), once without the
wind and once with TUNING_WIND=WIND (default 1), and measures each with
examples/organ_wind_measure.py's own measure_pipe: the noise between the
partials, the partials' skirts, the wander. Against it, the medians measured
from Pitea's pipes of the same families (sources.md) -- themselves a LOWER
BOUND, that set being noise-reduced -- and the attack: the noise between
the partials in the first 80 ms against the sustain's, the reeds' rush.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import organ_wind_measure as M                          # noqa: E402

RANKS = (("principal 8", "principal", 1 << 0), ("flute 8", "flute", 1 << 6),
         ("reed 8", "reed", 1 << 8))
NOTES = (48, 60, 72, 84)
PITEA = {"principal": (-31.0, -26.4), "flute": (-27.0, -24.5), "reed": (-33.0, -32.0)}  # noise, skirt
# the attack's noise against the sustain's, first 80 ms, by octave C3..C6 (the
# reeds' rush, which wind_attack_db is fitted to; the flues' for comparison)
PITEA_ATTACK = {"reed": (14.5, 14.0, 12.6, 10.0)}
# (and the wander, which fitted the bands' widths: principal 0.47/0.35 c and
# 0.24/0.30 dB at C4/C5; flute 0.94/0.71 c and 0.27/0.49 dB; reed 0.20/0.15 c
# and 0.11/0.26 dB -- sources.md)


def render(rank_bits, note, wind, out):
    import mido
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=19, time=0))
    t.append(mido.Message("control_change", control=11, value=rank_bits & 0x7F, time=0))
    t.append(mido.Message("control_change", control=43, value=(rank_bits >> 7) & 0x7F, time=0))
    t.append(mido.Message("note_on", note=note, velocity=100, time=10))
    t.append(mido.Message("note_off", note=note, time=3360))
    mid = out[:-4] + ".mid"
    m.save(mid)
    env = dict(os.environ, TUNING_REFLECT="0", TUNING_WIND=str(wind), TUNING_REGISTER="0")
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, out, "even"],
                   env=env, check=True, stdout=subprocess.DEVNULL)


def main(argv):
    a = [x for x in argv[1:] if not x.startswith("--")]
    wind = a[0] if a else "1"
    d = argv[argv.index("--keep") + 1] if "--keep" in argv else tempfile.mkdtemp(prefix="organwind_")
    os.makedirs(d, exist_ok=True)
    print("%-12s %4s | %-21s | %-21s | Pitea (noise, skirt) | attack, Pitea"
          % ("rank", "note", "no wind: noise  skirt", "wind %s: noise  skirt" % wind))
    for name, fam, bits in RANKS:
        for i, note in enumerate(NOTES):
            got = []
            for w in ("0", wind):
                out = os.path.join(d, "%s_%d_w%s.wav" % (fam, note, w))
                render(bits, note, w, out)
                m = M.measure_pipe(out, None, 440.0 * 2 ** ((note - 69) / 12.0))
                got.append(m)
            if None in got:
                print("%-12s %4d | (no plateau)" % (name, note))
                continue
            pa = PITEA_ATTACK.get(fam)
            print("%-12s %4d | %8.1f %8.1f dB | %8.1f %8.1f dB | %6.1f %6.1f        | %+5.1f %s"
                  % (name, note, got[0]["noise_db"], got[0]["skirt_db"], got[1]["noise_db"],
                     got[1]["skirt_db"], PITEA[fam][0], PITEA[fam][1], got[1]["attack_db"],
                     "%+5.1f" % pa[i] if pa else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
