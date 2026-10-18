#!/usr/bin/env python3
"""Neptune for a 7.1.4 room: neptune.py's piece, as a bed for Seth's speakers.

    python3 examples/neptune_714.py [OUTDIR] [--layout examples/brother_714.yaml]
                                    [--br 448000] [--keep]

The same MIDI, tuner, hall and wetness as neptune.py (it builds the MIDI
through neptune.build_midi), rendered twice per half: once as objects, dry of
reflections, for the speakers, and once as ordinary stereo, which sets the
levels and feeds the hall. immersive.bed then gives each half its direct sound
panned at the room's real angles, its first-order reflections panned to where
each wall's image stands, and the hall on eleven decorrelated speakers.

FOR A ROOM THAT REMOVES ITSELF. Seth's receiver corrects for its room, so the
room heard is the one in the file: the early reflections are back (immersive's
docstring), not only the tail.

THE RECESSION is neptune.py's, on the chorus's half: from 445 to 524 s its
direct sound -- here with its reflections, as in the stereo render, where they
are part of the dry -- falls 40 dB and darkens on recede.py's closing one-pole,
and its hall falls 28 dB.

THE BITRATE fits the 30 MiB upload: nine minutes at 576 kbit/s is 38 MB, so
448 kbit/s (about 30 MB with the container).
"""
import math
import os
import subprocess
import sys

import numpy as np
from scipy.signal import lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import neptune as N                                     # noqa: E402
import immersive as I                                   # noqa: E402
import recede as R                                      # noqa: E402


def render(mid, wav, objdir, env):
    br = os.path.join(ROOT, "blockrender.py")
    if not os.path.exists(wav):
        N.run([sys.executable, br, mid, wav, N.TUNER], env)
    done = os.path.isdir(objdir) and any(f.endswith('.objects.json') for f in os.listdir(objdir))
    if not done:
        N.run([sys.executable, br, mid, wav + ".unused.wav", N.TUNER,
               "--objects", objdir, "--by-source", "--no-reflect"], env)


class Recede:
    """recede.py's motion on a 12-channel block stream: the direct falls
    END_DB and the one-pole's corner closes with it; the hall falls HALL_DB."""

    SUB = 256          # frames per coefficient step of the closing filter

    def __init__(self, sr, t0, t1, direct_db, hall_db):
        self.sr, self.t0, self.t1 = sr, t0, t1
        self.direct_db, self.hall_db = direct_db, hall_db
        self.zi = np.zeros((1, 12))

    def frac(self, a, n):
        t = (a + np.arange(n)) / float(self.sr)
        return np.clip((t - self.t0) / (self.t1 - self.t0), 0.0, 1.0)

    def direct(self, a, x):
        f = self.frac(a, len(x))
        x = x * (10.0 ** (f * self.direct_db / 20.0))[:, None]
        y = np.empty_like(x)
        for i in range(0, len(x), self.SUB):
            fc = R.START_HZ * 10.0 ** (f[i] * -R.END_HZ_DECADES)
            al = 1.0 - math.exp(-2.0 * math.pi * fc / self.sr)
            y[i:i + self.SUB], self.zi = lfilter([al], [1.0, al - 1.0], x[i:i + self.SUB],
                                                 axis=0, zi=self.zi)
        return y

    def hall(self, a, x):
        return x * (10.0 ** (self.frac(a, len(x)) * self.hall_db / 20.0))[:, None]


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith('--')]
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d   # noqa: E731
    layout = opt('--layout', os.path.join(HERE, 'brother_714.yaml'))
    br = opt('--br', '448000')
    pos = [a for a in pos if a not in (layout, br)]
    out = pos[0] if pos else os.path.expanduser("~/Downloads/neptune_714")
    keep = '--keep' in argv
    os.makedirs(out, exist_ok=True)
    P = lambda name: os.path.join(out, name)                          # noqa: E731
    src = P("neptune_crm.mid")
    if not os.path.exists(src):
        N.run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", src, N.URL])

    print("building the MIDI")
    chorus = N.build_midi(src, P("neptune_tool.mid"))
    N.split(P("neptune_tool.mid"), False, P("neptune_band.mid"))
    N.split(P("neptune_tool.mid"), True, P("neptune_chorus.mid"))
    env = {"TUNING_ROOM": N.ROOM, "TUNING_WET": N.WET}
    voc = {"TUNING_VOCALISE": ",".join("%d=V" % c for c in sorted(set(chorus.values()))),
           "TUNING_VOICE_PARTS": ",".join("%d=%s" % (c, N.VOICES[n]) for n, c in sorted(chorus.items()))}
    os.environ.update(env)          # immersive's room and tail read the same

    print("rendering")
    render(P("neptune_band.mid"), P("np_band.wav"), P("obj_band"), env)
    render(P("neptune_chorus.mid"), P("np_chorus.wav"), P("obj_chorus"), dict(env, **voc))

    print("the band's bed")
    band, sr = I.bed(P("obj_band"), P("np_band.wav"), out, layout, N.ROOM, clean=not keep)
    t0, t1, direct_db, hall_db = N.RECEDE
    rc = Recede(sr, t0, t1, direct_db, hall_db)
    print("the chorus's bed, receding: direct %+.0f dB, its hall %+.0f dB, %.0f-%.0f s"
          % (direct_db, hall_db, t0, t1))
    cho, _ = I.bed(P("obj_chorus"), P("np_chorus.wav"), out, layout, N.ROOM, clean=not keep,
                   shape_direct=rc.direct, shape_hall=rc.hall)

    # the longer of the two, the other added into it
    big, small = (band, cho) if len(band) >= len(cho) else (cho, band)
    for a in range(0, len(small), I.BLOCK):
        b = small[a:a + I.BLOCK]
        big[a:a + len(b)] += b
    ok = I.finish(big, sr, out, "neptune", br, clean=True)
    del band, cho, big, small
    for f in ("np_band.bed.npy", "np_chorus.bed.npy"):
        os.remove(P(f))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
