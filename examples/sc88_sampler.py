#!/usr/bin/env python3
"""Samplers of GS variation tones, for Ben's ear: each program's capital tone
first, then its variations, each playing a phrase that suits what it is -- a
bass riff, a lead's line, a pad's chord, a bell's arpeggio, a stab.

    python3 examples/sc88_sampler.py OUT_DIR [group ...]

Groups (of sc88_synth.SC88_SYNTH, by program): bass, lead, pad, bell.
Writes OUT_DIR/sc88_<group>.wav (44.1 kHz) and a .txt of what plays when.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
os.environ.setdefault("TUNING_REFLECT", "0")

import mido
import numpy as np

import blockrender as B
import patch_map as P
from sc88_synth import SC88_SYNTH

TPB, TEMPO = 480, 500000            # 120 bpm


def group_of(p):
    if p in (35, 38, 39):
        return "bass"
    if p in (54, 80, 81, 82, 84, 86, 87, 101):
        return "lead"
    if p in (98, 102, 96, 103, 55, 62):
        return "bell" if p in (98, 102, 96, 103) else "stab"
    return "pad"


# (notes, start beat, length in beats) per phrase kind
PHRASES = {
    "bass": [(36, 0, .5), (39, .5, .5), (43, 1, .5), (48, 1.5, .5), (43, 2, .45), (46, 2.5, .6),
             (36, 3, 1.5)],
    "lead": [(60, 0, 1.05), (62, 1, 1.05), (63, 2, .5), (67, 2.5, .5), (72, 3, 2.0)],
    "pad": [(48, 0, 4), (55, 0, 4), (58, 0, 4), (63, 0, 4)],
    "bell": [(60, 0, 1), (67, .5, 1), (72, 1, 1), (75, 1.5, 2.5)],
    "stab": [(60, 0, .4), (63, 0, .4), (67, 0, .4), (60, 1, .4), (63, 1, .4), (67, 1, .4),
             (58, 2, 1.5), (62, 2, 1.5), (65, 2, 1.5)],
}
SPAN = {"bass": 5.5, "lead": 6, "pad": 7, "bell": 5, "stab": 5}     # beats, with its release


def tone_midi(p, b, kind):
    mf = mido.MidiFile(ticks_per_beat=TPB)
    t = mido.MidiTrack()
    mf.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=TEMPO))
    t.append(mido.Message("control_change", control=0, value=b))
    t.append(mido.Message("program_change", program=p))
    ev = []
    for n, s, d in PHRASES[kind]:
        ev.append((int(s * TPB), 1, n))
        ev.append((int((s + d) * TPB), 0, n))
    ev.sort()
    now = 0
    for at, on, n in ev:
        t.append(mido.Message("note_on" if on else "note_off", note=n, velocity=96 if on else 0,
                              time=at - now))
        now = at
    t.append(mido.MetaMessage("end_of_track", time=int(SPAN[kind] * TPB) - now))
    return mf


def main(argv):
    out = argv[1]
    groups = argv[2:] or ["bass", "lead", "pad", "bell"]
    for g in groups:
        progs = sorted({p for p, b in SC88_SYNTH if (group_of(p) in (g, "stab") if g == "bell"
                                                     else group_of(p) == g)})
        audio, log, at = [], [], 0.0
        for p in progs:
            for b in [0] + sorted(b for q, b in SC88_SYNTH if q == p):
                kind = group_of(p)
                L, R = B.render(tone_midi(p, b, kind))[:2]
                x = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)
                x = x[: int(SPAN[kind] * TEMPO / 1e6 * B.SR)]
                name = P.VARIATION_NAMES.get((p, b), "capital") if b else "capital (%d)" % p
                log.append("%6.1f s  %d.%d %s" % (at, p, b, name))
                audio += [x, np.zeros((int(.4 * B.SR), 2))]
                at += len(x) / B.SR + .4
        y = np.concatenate(audio)
        y *= 0.89 / max(1e-9, np.abs(y).max())
        B.write_wav(os.path.join(out, "sc88_%s.wav" % g), y[:, 0], y[:, 1])
        open(os.path.join(out, "sc88_%s.txt" % g), "w").write("\n".join(log) + "\n")
        print(g, "%.0f s" % at)


if __name__ == "__main__":
    main(sys.argv)
