"""A drum machine set, its fit at the last commit against its fit now, for
Ben's ear: every voice of the set once, then a groove -- 'old' rendered with HEAD's
tonelib.py and percussion_map.py (or DRUMKIT_AB_REF's), 'new' with the tree's.

    python3 examples/drumkit_ab.py KIT ATTR NAME    e.g. 25 tr808 tr808
        -> ~/Music/licence_refits/NAME_{old,new}.mp3
"""
import os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("DRUMKIT_AB_OLD"):            # the 'old' render: HEAD's tonelib.py first
    sys.path.insert(0, os.environ["DRUMKIT_AB_OLD"])
OUT = os.path.expanduser("~/Music/licence_refits")


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


def render(kit, name, tag):
    import blockrender as B, percussion_map as P
    from scipy.io import wavfile
    L, R = B.render(midi(kit, sorted(P.KITS.get(kit, {}))))[:2]
    y = np.stack([L, R], 1); y = y / (np.abs(y).max() + 1e-12) * 0.7
    w = os.path.join(OUT, "%s_%s.wav" % (name, tag))
    wavfile.write(w, B.SR, (y * 32767).astype(np.int16))
    subprocess.run(["lame", "--quiet", "-b", "256", w, w[:-4] + ".mp3"], check=True)
    os.remove(w)


def main(argv):
    """The whole voice file of the last commit against the tree's: every
    patch and every fitted attribute (a ROM cymbal's trims too)."""
    kit, name = int(argv[1]), argv[3]
    if len(argv) > 4:                       # a child: one render
        return render(kit, name, argv[4])
    import tempfile
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        for mod in ("tonelib.py", "percussion_map.py"):     # the patches and the kits' levels
            src = subprocess.run(["git", "show", os.environ.get("DRUMKIT_AB_REF", "HEAD") + ":" + mod],
                                 capture_output=True, text=True, check=True).stdout
            open(os.path.join(d, mod), "w").write(src)
        for tag in ("old", "new"):
            env = dict(os.environ, DRUMKIT_AB_OLD=d) if tag == "old" else dict(os.environ)
            env.pop("DRUMKIT_AB_OLD", None) if tag == "new" else None
            subprocess.run([sys.executable, os.path.abspath(__file__)] + argv[1:4] + [tag], env=env, check=True)
    print("written %s_{old,new}.mp3" % name)


if __name__ == "__main__":
    main(sys.argv)
