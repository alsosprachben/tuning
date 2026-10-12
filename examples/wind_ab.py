#!/usr/bin/env python3
"""The church organ's SHARED WIND by ear (wind.py, GM 19): one chest, its swing
under the pipes' demand at several flexibilities, for Ben to choose.

    python3 examples/wind_ab.py OUT.wav [CHORALE.mid] [--flex=0,1,2.5,8] [--stops=principal 8,octave 4]

Two passages, each at every flexibility in turn (0 = the shared wind off):
  HELD   middle C held through chords that enter and lift around it -- the
         coupling alone: its pitch and level dip as a chord takes the wind and
         surge as it gives it back
  CHORALE  the file's every voice on ONE channel (one division, one chest),
         program 19
Each through the matched hall (pitea_fit.PITEA_HALL), a spoken-free second
of silence between.
"""
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B  # noqa: E402
import tonelib as T  # noqa: E402
import pitea_fit as PF  # noqa: E402


def word_msgs(stops):
    names = [r[0] for r in T.FlueOrganProperties.stop_ranks]
    w = sum(1 << names.index(s) for s in stops)
    return [mido.Message("control_change", channel=0, control=43, value=(w >> 7) & 127, time=0),
            mido.Message("control_change", channel=0, control=11, value=w & 127, time=0)]


def held(stops):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.Message("program_change", channel=0, program=19, time=0))
    t.extend(word_msgs(stops))
    t.append(mido.Message("note_on", channel=0, note=60, velocity=100, time=0))
    gap = 960
    for ch in ((43, 52, 67, 72, 76), (41, 53, 65, 69, 77), (36, 48, 64, 67, 79)):
        for i, n in enumerate(ch):
            t.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=gap if i == 0 else 0))
        for i, n in enumerate(ch):
            t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=960 if i == 0 else 0))
    t.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=gap))
    return m


def chorale(path, stops):
    src = mido.MidiFile(path)
    m = mido.MidiFile(type=1, ticks_per_beat=src.ticks_per_beat)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.Message("program_change", channel=0, program=19, time=0))
    t.extend(word_msgs(stops))
    ev = []
    for tr in src.tracks:
        now = 0
        for msg in tr:
            now += msg.time
            if msg.type in ("note_on", "note_off"):
                ev.append((now, msg.copy(channel=0, time=0)))
            elif msg.type == "set_tempo":
                ev.append((now, msg.copy(time=0)))
    ev.sort(key=lambda e: (e[0], e[1].type == "note_on"))
    last = 0
    for at, msg in ev:
        t.append(msg.copy(time=at - last))
        last = at
    return m


def render(m, flex):
    fl = T.FlueOrganProperties
    keep = (fl.shared_wind, fl.wind_flex)
    fl.shared_wind, fl.wind_flex = flex > 0.0, flex
    try:
        L, R = B.render(m)[:2]
    finally:
        fl.shared_wind, fl.wind_flex = keep
    y = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)
    with tempfile.TemporaryDirectory() as d:
        from scipy.io import wavfile
        wavfile.write(os.path.join(d, "a.wav"), B.SR, (y / max(np.abs(y).max(), 1e-9) * 0.5).astype(np.float32))
        subprocess.run(["sox", os.path.join(d, "a.wav"), "-e", "floating-point", "-b", "32",
                        os.path.join(d, "b.wav")] + PF.PITEA_HALL.split(), check=True, stderr=subprocess.DEVNULL)
        return wavfile.read(os.path.join(d, "b.wav"))[1].astype(np.float64)


def main(argv):
    out = argv[1]
    src = next((a for a in argv[2:] if a.endswith(".mid")), None)
    flex = next((tuple(float(v) for v in a.split("=")[1].split(",")) for a in argv if a.startswith("--flex=")),
                (0.0, 1.0, 2.5, 8.0))
    stops = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--stops=")),
                 ["principal 8", "octave 4"])
    parts = [render(held(stops), f) for f in flex]
    if src:
        parts += [render(chorale(src, stops), f) for f in flex]
    gap = np.zeros((B.SR, 2))
    z = np.concatenate([np.concatenate([p, gap]) for p in parts])
    z *= 0.5 / np.abs(z).max()
    from scipy.io import wavfile
    wavfile.write(out, B.SR, (z * 32767).astype(np.int16))
    print("  wrote %s: held%s, at flexibility %s" % (out, " then chorale" if src else "", ", ".join("%g" % f for f in flex)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
