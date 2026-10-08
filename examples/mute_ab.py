#!/usr/bin/env python3
"""The harmon mute, by ear: before and after, at one gain a pair.

    python3 examples/mute_ab.py [outdir]

GM 59 as it was before examples/mute_fit.py (a straight mute from theory: the
bell's cutoff at 2.4 kHz, one cavity peak at 1.9 kHz, -5 dB) and as it is now
(the measured harmon, stem out), in the hall, hybrid440, master -14 dB,
through roomtail -- examples/pizz_ab.py's recipe:

  ballad     a slow line in the trumpet's middle, mp, each note held
  alright    the first 45 s of alright.mid, whose GM 59 plays from the start

One gain a pair, so the mute's level against the old one is heard as it is.
Default outdir ~/Downloads/mute.
"""
import os
import runpy
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

from pizz_ab import peak  # noqa: E402

TUNE = ((67, 2), (70, 1), (72, 1), (74, 3), (72, 1), (70, 2), (67, 2), (65, 1), (67, 3), (62, 4),
        (67, 2), (70, 1), (74, 1), (77, 3), (75, 1), (74, 2), (72, 2), (70, 2), (67, 6))


def ballad(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=750000, time=0))
    t.append(mido.Message("program_change", program=59, time=0))
    for n, b in TUNE:
        t.append(mido.Message("note_on", note=n, velocity=70, time=0))
        t.append(mido.Message("note_off", note=n, time=480 * b))
    m.save(dst)
    return dst


def render(mid, wav, which):
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_MASTER_DB="-14")
    dry = wav[:-4] + "_dry.wav"
    subprocess.run([sys.executable, os.path.abspath(__file__), "--blockrender", which, mid, dry],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    import lib
    lib.roomtail(dry, wav, env={"TUNING_ROOM": "hall"})
    return wav


def blockrender(which, mid, dry):
    sys.path.insert(0, HERE)
    if which == "old":
        import tonelib as T
        M = T.MutedTrumpetProperties

        def old_bore_gain(self, partial_hz):
            g = T.TrumpetProperties.bore_gain(self, partial_hz)
            r = partial_hz / self.mute_resonance_hz
            if r > 0.0:
                boost = 10.0 ** (self.mute_resonance_db / 20.0) - 1.0
                g *= 1.0 + boost / (1.0 + (self.mute_resonance_q * (r - 1.0 / r)) ** 2)
            return g
        for k, v in dict(bore_gain=old_bore_gain, directivity_radius=0.025, bell_cutoff_hz=2400.0,
                         bell_order=5.0, mute_resonance_hz=1900.0, mute_resonance_q=1.4,
                         mute_resonance_db=6.0,
                         initial_gain=T.TrumpetProperties.initial_gain * 10 ** (-5.0 / 20)).items():
            setattr(M, k, v)
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/mute")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="mute_")
    p = os.path.join(d, "alright.mid")
    excerpt(os.path.expanduser("~/Downloads/midi/alright.mid"), 45.0).save(p)
    srcs = {"ballad": ballad(os.path.join(d, "ballad.mid")), "alright": p}
    pair = ("old", "new")
    for name, mid in srcs.items():
        w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)), k) for k in pair}
        gain = -1.0 - 20 * np.log10(max(peak(q) for q in w.values()))
        for i, k in enumerate(pair):
            mp3 = os.path.join(out, "mute_%s_%d_%s.mp3" % (name, i + 1, k))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
