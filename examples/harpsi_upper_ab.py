"""The harpsichord's upper 8' alone, its old fit (the Harpsimachord's) against
its new (VCSL's Flemish pair), for Ben's ear: a short passage on GM 6 with only
the upper 8' drawn (CC11 = 2), then the same with both 8's (CC11 = 3).

    python3 examples/harpsi_upper_ab.py      -> ~/Music/licence_refits/harpsi_upper8_{old,new}.mp3
"""
import os, sys, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.expanduser("~/Music/licence_refits")
OLD = dict(tonal_dampening=0.756, decay_db=4.62 * 1.12, harmonic_decay_db=2.29 * 1.12)


def midi():
    import mido
    m = mido.MidiFile(type=0, ticks_per_beat=480); t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.Message('program_change', program=6, time=0))
    seq = [(60, 64, 67), (62,), (64,), (65,), (67, 71, 74), (69,), (71,), (72, 76, 79), (48, 55, 60, 64), (36, 48)]
    for word in (2, 3):
        t.append(mido.Message('control_change', control=11, value=word, time=0))
        for notes in seq:
            for k in notes:
                t.append(mido.Message('note_on', note=k, velocity=90, time=0))
            dur = 1440 if len(notes) > 1 else 240
            t.append(mido.Message('note_off', note=notes[0], velocity=0, time=dur))
            for k in notes[1:]:
                t.append(mido.Message('note_off', note=k, velocity=0, time=0))
        t.append(mido.Message('note_off', note=0, velocity=0, time=1920))
    return m


def main():
    import blockrender as B, tonelib as T
    from scipy.io import wavfile
    os.makedirs(OUT, exist_ok=True)
    new = {k: getattr(T.HarpsiUpperProperties, k) for k in OLD}
    for tag, vals in (("old", OLD), ("new", new)):
        for k, v in vals.items():
            setattr(T.HarpsiUpperProperties, k, v)
        L, R = B.render(midi())[:2]
        y = np.stack([L, R], 1); y = y / (np.abs(y).max() + 1e-12) * 0.7
        w = os.path.join(OUT, "harpsi_upper8_%s.wav" % tag)
        wavfile.write(w, B.SR, (y * 32767).astype(np.int16))
        subprocess.run(["lame", "--quiet", "-b", "256", w, w[:-4] + ".mp3"], check=True)
        os.remove(w)
    print("written:", sorted(f for f in os.listdir(OUT) if f.startswith("harpsi_upper8")))


if __name__ == "__main__":
    main()
