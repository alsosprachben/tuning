#!/usr/bin/env python3
"""The gunshot's distance, by ear: CC91 at 40, 90 and 127.

    python3 examples/gunshot_distance_ab.py [SCORE.mid] [SECONDS] [outdir]

GM 127 is a click and the room is its tail (tonelib.GunshotProperties). CC91
in this renderer is a distance from the microphone in the one shared room:
GM's default 40 is the nominal distance, 90 is 2.25 times it and 127 is 3.2
times (11.8 m in the hall, past the 6-7.8 m where the room overtakes the
direct sound). The direct sound is held fixed; only the room's share grows.

Two scores, each rendered at the three sends and written as MP3s at one gain
per score, so their levels compare:

  ateam    the opening of A-Team (default ~/Downloads/midi/A-Team.mid, the
           gun on channel 10): six shots a quarter-second apart, then the band
           at its own default distance. The send is set on the gun's channel
           only.
  alone    three shots, 3 s apart, nothing else -- so each tail is heard out.

Hall, hybrid440, master -14 dB, roomtail: render-corpus.sh's recipe. Default
12 s of A-Team into ~/Downloads/gunshot.
"""
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

SENDS = (40, 90, 127)
GUN = 127


def with_send(src, dst, send):
    """src with CC91 = send on every channel that plays the gunshot."""
    m = mido.MidiFile(src)
    for tr in m.tracks:
        chans = {e.channel for e in tr if e.type == "program_change" and e.program == GUN}
        for ch in sorted(chans):
            tr.insert(0, mido.Message("control_change", channel=ch, control=91, value=send, time=0))
    m.save(dst)


def alone(dst, gap=3.0, shots=3):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=10, program=GUN, time=0))
    tk = int(gap * 960)
    for i in range(shots):
        t.append(mido.Message("note_on", channel=10, note=55, velocity=120, time=10 if i == 0 else tk - 120))
        t.append(mido.Message("note_off", channel=10, note=55, time=120))
    t.append(mido.Message("note_off", channel=10, note=55, time=tk))
    m.save(dst)


def render(mid, out):
    import lib
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_MASTER_DB="-14")
    dry = out[:-4] + "_dry.wav"
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    lib.roomtail(dry, out, env={"TUNING_ROOM": "hall"})
    return out


def peak(p):
    s = subprocess.run(["sox", p, "-n", "stat"], capture_output=True, text=True).stderr
    return max(abs(float([l for l in s.splitlines() if l.startswith(k)][0].split()[-1]))
               for k in ("Maximum amplitude", "Minimum amplitude"))


def main(argv):
    from bitident import excerpt
    score = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/midi/A-Team.mid")
    secs = float(argv[2]) if len(argv) > 2 else 12.0
    out = argv[3] if len(argv) > 3 else os.path.expanduser("~/Downloads/gunshot")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="gunshot_")
    cut = os.path.join(d, "ateam_%ds.mid" % secs)
    excerpt(score, secs).save(cut)
    solo = os.path.join(d, "alone.mid")
    alone(solo)
    for name, src in (("ateam", cut), ("alone", solo)):
        wavs = {}
        for s in SENDS:
            mid = os.path.join(d, "%s_cc91_%d.mid" % (name, s))
            with_send(src, mid, s)
            wavs[s] = render(mid, mid[:-4] + ".wav")
        gain = -1.0 - 20 * np.log10(max(peak(p) for p in wavs.values()))
        for i, (s, p) in enumerate(wavs.items()):
            mp3 = os.path.join(out, "gunshot_%s_%d_cc91_%d.mp3" % (name, i + 1, s))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", p, "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
