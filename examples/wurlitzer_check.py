#!/usr/bin/env python3
"""THE DIVIDER ORGAN CHECKED: each tab drawn alone (tonelib.DividerOrganProperties),
rendered in-process on C3, C4 and C5 with no room, its harmonics 1-8 against the
tables it was fitted to (examples/wurlitzer_fit.py) -- dB rms per key.

    TUNING_REFLECT=0 python3 examples/wurlitzer_check.py ["Flute 8'" ...]
"""
import sys, math, numpy as np, mido
import os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'examples'))
import patch_map as P, tonelib as T, blockrender as B, wurlitzer_survey as WS
WS.SR = B.SR
D = T.DividerOrganProperties
names = [r[0] for r in D.stop_ranks]
def render(cls, keys=(48, 60, 72), secs=2.0):
    P.PROGRAM_CLASS[16] = cls
    m = mido.MidiFile(type=1, ticks_per_beat=480); t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=16, time=0))
    for k in keys:
        t.append(mido.Message("note_on", channel=0, note=k, velocity=100, time=int(0.5 * 960)))
        t.append(mido.Message("note_off", channel=0, note=k, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, float) + np.asarray(R, float))
def harm(x, keys=(48, 60, 72), secs=2.0, ratio=1.0):
    out = []
    t = 0.0
    for k in keys:
        t += 0.5; s, e = t + 0.4, t + secs - 0.2; t += secs
        f = 440 * 2 ** ((k - 69) / 12) * ratio
        f0, h = WS.spectrum(x[int(s * B.SR):int(e * B.SR)], f)
        out.append((f0, h))
    return out
if __name__ == '__main__':
    for tab in (sys.argv[1:] or names):
        i = names.index(tab); r = D.stop_ranks[i]
        x = render(type("Tab", (D,), dict(default_stops=1 << i)))
        sp = T.rank_spectrum(r[3])(261.63, 0, 1, 1)
        for (f0, h), k in zip(harm(x, ratio=r[1]), (48, 60, 72)):
            tb = np.array(sp.mode_gains_at(440 * 2 ** ((k - 69) / 12) * r[1]))[:8]
            tb = 20 * np.log10(tb / tb.max() + 1e-9)
            err = np.sqrt(np.mean(np.clip(h[:8] - tb, -30, 30) ** 2))
            print("%-18s %3d  render %s\n%-18s      table  %s   (rms %.1f dB)" % (
                tab, k, " ".join("%4.0f" % v for v in h[:8]), "", " ".join("%4.0f" % v for v in tb), err))
