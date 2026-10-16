#!/usr/bin/env python3
"""The Room (program 8) and Power (16) sets beside Standard, for the ear.

    python3 -I examples/roomset_ab.py [OUTDIR]        # default ~/Downloads/roomset_ab

One rock groove three times -- four bars on Standard, four on Room, four on
Power, each ending in a fill down the six toms -- then each set's toms and
kick alone. Rendered WITH the room (the Room set's live room is its
reflections), and the same file through GeneralUser GS's three sets
(timidity: measured only, a local reference, never redistributed); the two
loudness-matched as examples/tr808_ab.py does.
"""
import os
import subprocess
import sys
import tempfile
import warnings

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")
import tr808_ab as A          # noqa: E402  (finish: reverb and loudness)

TPB = 480
GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
A.LOUD_DB = -30.0
SETS = (0, 8, 16)


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 108), time=0))
    ev, q, e8 = [], TPB, TPB // 2
    t = 0
    for kit in SETS:
        ev.append((t, "pc", kit))
        for bar in range(4):
            t0 = t + bar * 4 * q
            ev += [(t0 + k * e8, 42, 85 if k % 2 == 0 else 60) for k in range(8)]
            ev += [(t0, 36, 110), (t0 + 2 * q + e8, 36, 95), (t0 + q, 38, 110), (t0 + 3 * q, 38, 115)]
            if bar == 3:
                ev = [e for e in ev if not (e[0] >= t0 + 2 * q and e[1] in (38, 42))]
                for k, n in enumerate((50, 48, 47, 45, 43, 41)):
                    ev.append((t0 + 2 * q + k * (2 * q // 6), n, 105))
        t += 16 * q
        ev += [(t, 36, 110), (t, 49, 100)]
        t += 4 * q
    for kit in SETS:
        ev.append((t, "pc", kit))
        for n in (36, 41, 45, 50):
            ev.append((t, n, 105)); t += 2 * q
        t += 2 * q
    msgs = []
    for at, n, v in ev:
        if n == "pc":
            msgs.append((at, 0, mido.Message("program_change", channel=9, program=v)))
        else:
            msgs.append((at, 2, mido.Message("note_on", channel=9, note=n, velocity=v)))
            msgs.append((at + 60, 1, mido.Message("note_off", channel=9, note=n, velocity=0)))
    msgs.sort(key=lambda r: (r[0], r[1]))
    now = 0
    for at, _o, msg in msgs:
        tr.append(msg.copy(time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=8 * q))
    m.save(path)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/roomset_ab")
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "roomset.mid")
    build(mid)
    env = {k: v for k, v in os.environ.items() if k != "TUNING_REFLECT"}       # the room ON
    subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"), mid,
                           os.path.join(out, "ours.dry.wav"), "hybrid"], env=env, cwd=HERE)
    A.finish(os.path.join(out, "ours.dry.wav"), os.path.join(out, "ours.mp3"))
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "k.cfg")
        with open(cfg, "w") as f:
            for kit in SETS:
                f.write("drumset %d\n" % kit)
                for n in range(27, 88):
                    f.write('%d %%font "%s" 128 %d %d\n' % (n, GU, kit, n))
        subprocess.check_call(["timidity", "-c", cfg, "-Ow", "-o", os.path.join(out, "gu.dry.wav"),
                               "-s", "44100", "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        A.finish(os.path.join(out, "gu.dry.wav"), os.path.join(out, "gu.mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
