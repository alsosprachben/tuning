#!/usr/bin/env python3
"""A/B for a GM program between two trees: a phrase of staccato chords and a
line, the program as it plays (its own default registration and rotor).

    python3 examples/program_ab.py render TREE PROGRAM OUT.npz
    python3 examples/program_ab.py ab BEFORE.npz AFTER.npz OUT.mp3

Run `render` once with each tree (it renders through the TREE it is given),
then `ab`: before, then after, one normalisation for the pair.
"""
import os
import subprocess
import sys

import numpy as np


def phrase(B, program):
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=program, time=0))
    ev = []
    # staccato chords on the beat: C, F, G, C
    for k, ch in enumerate(((48, 60, 64, 67), (53, 60, 65, 69), (55, 59, 62, 67), (48, 60, 64, 67))):
        for n in ch:
            ev.append((k * 480, k * 480 + 200, n))
    # then a line, legato and detached
    t0 = 4 * 480
    for k, n in enumerate((72, 74, 76, 77, 79, 77, 76, 74, 72)):
        ev.append((t0 + k * 240, t0 + k * 240 + (230 if k % 2 else 120), n))
    ev.append((t0 + 9 * 240, t0 + 9 * 240 + 960, 72))
    ev.append((t0 + 9 * 240, t0 + 9 * 240 + 960, 60))
    msgs = sorted([(a, 1, n) for a, _, n in ev] + [(b, 0, n) for _, b, n in ev])
    last = 0
    for at, on, n in msgs:
        t.append(mido.Message("note_on" if on else "note_off", channel=0, note=n,
                              velocity=96 if on else 0, time=at - last))
        last = at
    t.append(mido.MetaMessage("end_of_track", time=960))
    L, R = B.render(m)[:2]
    return np.stack([np.asarray(L, np.float32), np.asarray(R, np.float32)], 1), B.SR


def render(tree, program, out):
    sys.path[:0] = [tree, os.path.join(tree, "examples")]
    import blockrender as B
    x, sr = phrase(B, int(program))
    np.savez(out, x=x, sr=sr)
    print("%s: program %s rendered" % (tree, program))


def ab(before, after, out):
    from scipy.io import wavfile
    a, b = np.load(before), np.load(after)
    sr = int(a["sr"])
    pk = max(np.abs(a["x"]).max(), np.abs(b["x"]).max(), 1e-9)
    gap = np.zeros((int(1.0 * sr), 2), np.float32)
    w = 0.9 * np.concatenate([a["x"] / pk, gap, b["x"] / pk])
    wav = out[:-4] + ".wav"
    wavfile.write(wav, sr, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "--quiet", "-V2", wav, out])
    print("  -> " + out)


if __name__ == "__main__":
    if sys.argv[1] == "render":
        render(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        ab(sys.argv[2], sys.argv[3], sys.argv[4])
