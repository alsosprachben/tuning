"""A drum machine set, its fit at the last commit against its fit now, for
Ben's ear: one bar of every voice the set's fit scripts touch, then a groove --
the `trXXX = {...}` patches read off HEAD's tonelib.py and set for the 'old' render.

    python3 examples/drumkit_ab.py KIT ATTR NAME    e.g. 25 tr808 tr808
        -> ~/Music/licence_refits/NAME_{old,new}.mp3
"""
import ast, os, re, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.expanduser("~/Music/licence_refits")


def old_patches(attr):
    src = subprocess.run(["git", "show", "HEAD:tonelib.py"], capture_output=True, text=True, check=True).stdout
    out = {}
    for m in re.finditer(r"\nclass (\w+)\([^)]*\):", src):
        body = src[m.end():]
        nxt = re.search(r"\nclass \w+", body)
        body = body[:nxt.start()] if nxt else body
        k = re.search(r"\n    %s = (\{)" % attr, body)
        if not k:
            continue
        i = k.start(1); depth = 0
        for j in range(i, len(body)):
            depth += {"{": 1, "}": -1}.get(body[j], 0)
            if depth == 0:
                import tonelib as _T
                out[m.group(1)] = eval(body[i:j + 1], dict(vars(_T))); break
    return out


def midi(kit, notes):
    import mido
    m = mido.MidiFile(type=0, ticks_per_beat=480); t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.Message('program_change', channel=9, program=kit, time=0))
    for n in notes:                                   # each voice alone
        t.append(mido.Message('note_on', channel=9, note=n, velocity=110, time=0))
        t.append(mido.Message('note_off', channel=9, note=n, velocity=0, time=480))
    groove = [(0, 36), (0, 42), (240, 42), (480, 38), (480, 42), (720, 42), (960, 36), (960, 42),
              (1200, 36), (1200, 46), (1440, 38), (1440, 42), (1680, 42)]
    now = 0
    for bar in range(4):
        for at, n in groove:
            tk = bar * 1920 + at + 960
            t.append(mido.Message('note_on', channel=9, note=n, velocity=110, time=tk - now)); now = tk
            t.append(mido.Message('note_off', channel=9, note=n, velocity=0, time=0))
    t.append(mido.Message('note_off', channel=9, note=36, velocity=0, time=1920))
    return m


def main(argv):
    kit, attr, name = int(argv[1]), argv[2], argv[3]
    import blockrender as B, tonelib as T, percussion_map as P
    from scipy.io import wavfile
    notes = sorted(n for n in P.KITS.get(kit, {}))
    old = old_patches(attr)
    new = {c: getattr(T, c).__dict__[attr] for c in old if hasattr(T, c) and attr in getattr(T, c).__dict__}
    os.makedirs(OUT, exist_ok=True)
    for tag, pat in (("old", old), ("new", new)):
        for c, d in pat.items():
            if hasattr(T, c):
                setattr(getattr(T, c), attr, d)
        L, R = B.render(midi(kit, notes))[:2]
        y = np.stack([L, R], 1); y = y / (np.abs(y).max() + 1e-12) * 0.7
        w = os.path.join(OUT, "%s_%s.wav" % (name, tag))
        wavfile.write(w, B.SR, (y * 32767).astype(np.int16))
        subprocess.run(["lame", "--quiet", "-b", "256", w, w[:-4] + ".mp3"], check=True)
        os.remove(w)
    print("written %s_{old,new}.mp3; %d classes, %d changed" % (
        name, len(old), sum(old[c] != new.get(c) for c in old)))


if __name__ == "__main__":
    main(sys.argv)
