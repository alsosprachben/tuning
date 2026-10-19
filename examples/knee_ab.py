#!/usr/bin/env python3
"""A/B for a renderer change, from two trees: a piano note and the claves
struck 16 times at 80 bpm (each strike at a different place in its 512-sample
block), then 20 s of a corpus file.

    python3 examples/knee_ab.py render TREE OUT.npz [MID]   one tree's takes
    python3 examples/knee_ab.py ab BEFORE.npz AFTER.npz OUT.mp3

Run `render` with each tree's own python path (the file renders through the
TREE it is given), then `ab`. Prints each repeated note's spread: how much its
first 50 ms differs strike to strike -- a position-dependent attack shows as
a spread the block-aligned strike does not have.
"""
import os
import subprocess
import sys

import numpy as np


def strikes(B, program, note, kit=False, beat_s=0.75, n=16, hold=0.3):
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    ch = 9 if kit else 0
    t.append(mido.MetaMessage("set_tempo", tempo=int(round(beat_s * 1e6)), time=0))
    t.append(mido.Message("program_change", channel=ch, program=program, time=0))
    gap = 480
    off = int(hold / beat_s * 480)
    for _ in range(n):
        t.append(mido.Message("note_on", channel=ch, note=note, velocity=96, time=gap))
        t.append(mido.Message("note_off", channel=ch, note=note, velocity=0, time=off))
        gap = 480 - off
    t.append(mido.MetaMessage("end_of_track", time=960))
    L, R = B.render(m)[:2]
    x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    sr = B.SR
    e = []
    for k in range(n):
        on = int(round((1 + k) * beat_s * sr))
        seg = x[on - 200:on + int(0.08 * sr)]
        a = on - 200 + int(np.argmax(np.abs(seg) > 0.2 * np.abs(seg).max()))
        e.append(10 * np.log10(np.sum(x[a:a + int(0.05 * sr)] ** 2) + 1e-20))
    return x.astype(np.float32), float(np.ptp(e))


def render(tree, out, mid=None):
    sys.path[:0] = [tree, os.path.join(tree, "examples")]
    os.environ.setdefault("TUNING_REFLECT", "0")
    import blockrender as B
    import bitident as BI
    piano, sp = strikes(B, 0, 72)
    claves, sc = strikes(B, 0, 75, kit=True)
    takes = dict(piano=piano, claves=claves)
    if mid:
        L, R = B.render(BI.excerpt(mid, 20))[:2]
        takes["piece"] = (0.5 * (np.asarray(L, float) + np.asarray(R, float))).astype(np.float32)
    np.savez(out, sr=B.SR, **takes)
    print("%s: piano C5 spread %.1f dB, claves spread %.1f dB" % (tree, sp, sc))


def ab(before, after, out):
    a, b = np.load(before), np.load(after)
    sr = int(a["sr"])
    gap = np.zeros(int(0.8 * sr), np.float32)
    parts = []
    for k in ("piano", "claves", "piece"):
        if k in a and k in b:
            pk = max(np.abs(a[k]).max(), np.abs(b[k]).max(), 1e-9)
            parts += [a[k] / pk, gap, b[k] / pk, gap, gap]
    w = 0.9 * np.concatenate(parts)
    wav = out[:-4] + ".wav"
    from scipy.io import wavfile
    wavfile.write(wav, sr, (np.stack([w, w], 1) * 32767).astype(np.int16))
    subprocess.check_call(["lame", "--quiet", "-V2", wav, out])
    print("  -> " + out)


if __name__ == "__main__":
    if sys.argv[1] == "render":
        render(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        ab(sys.argv[2], sys.argv[3], sys.argv[4])
