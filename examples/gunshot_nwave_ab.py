#!/usr/bin/env python3
"""The gunshot as an N-wave, by ear: three calibres, and A-Team.

    python3 examples/gunshot_nwave_ab.py [--ref CLICK.wav] [outdir]

GM 127 is now a pressure pulse (tonelib.pulse_series), its length set by the
key so that its spectrum peaks on the key's frequency. Rendered here, each at
its default distance (127's, tonelib.GunshotProperties.reverb_distance), in the
hall, hybrid440, master -14 dB, through roomtail -- render-corpus.sh's recipe:

  calibres   one shot each on G4, G3 and G2, 3 s apart: 1.7, 3.4 and 6.7 ms.
             A-Team writes its shots around G3.
  ateam      the first 12 s of A-Team (~/Downloads/midi/A-Team.mid).

--ref adds a render of the old click (examples/gunshot_distance_ab.py's
`alone` at CC91 127, made before the N-wave) at the same gain, so the levels
compare. Default outdir ~/Downloads/gunshot.
"""
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

from gunshot_distance_ab import peak, render  # noqa: E402

CALIBRES = (67, 55, 43)


def calibres(dst, gap=3.0):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=10, program=127, time=0))
    tk = int(gap * 960)
    for i, n in enumerate(CALIBRES):
        t.append(mido.Message("note_on", channel=10, note=n, velocity=120, time=tk if i == 0 else tk - 120))
        t.append(mido.Message("note_off", channel=10, note=n, time=120))
    t.append(mido.Message("note_off", channel=10, note=CALIBRES[-1], time=tk))
    m.save(dst)


def mp3(wav, dst, gain, d):
    tmp = os.path.join(d, "g.wav")
    subprocess.run(["sox", wav, "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
    subprocess.run(["lame", "-b", "320", "--quiet", tmp, dst], check=True)
    print("  -> %s" % dst)


def main(argv):
    from bitident import excerpt
    ref = argv[argv.index("--ref") + 1] if "--ref" in argv else None
    rest = [a for i, a in enumerate(argv[1:], 1) if a != "--ref" and argv[i - 1] != "--ref"]
    out = rest[0] if rest else os.path.expanduser("~/Downloads/gunshot")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="nwave_")
    cal = os.path.join(d, "calibres.mid")
    calibres(cal)
    cut = os.path.join(d, "ateam_12s.mid")
    excerpt(os.path.expanduser("~/Downloads/midi/A-Team.mid"), 12.0).save(cut)
    wavs = {"calibres": render(cal, cal[:-4] + ".wav"), "ateam": render(cut, cut[:-4] + ".wav")}
    if ref:
        wavs["click_ref"] = ref
    gain = -1.0 - 20 * np.log10(max(peak(p) for p in wavs.values()))
    for name, p in wavs.items():
        mp3(p, os.path.join(out, "nwave_%s.mp3" % name), gain, d)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
