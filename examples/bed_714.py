#!/usr/bin/env python3
"""Any score to a 7.1.4 MPEG-H bed for Seth's room, with the settings it was
rendered with in stereo.

    python3 examples/bed_714.py SCORE.mid OUTDIR [--tuner hybridmean:466]
            [--room church] [--wet -3] [--master-db -12] [--br 576000]
            [--layout examples/brother_714.yaml]

Renders SCORE twice -- stereo (which sets the levels and feeds the hall) and
as objects dry of reflections -- with one environment, then runs
examples/immersive.py: the direct sound at the room's real angles, the first
reflections placed in direction, the tail on eleven speakers. Both renders come
from the same code, so the levels the stereo sets are the objects' own.

E.g. a BuxWV 161 version: its buxwv161_graded.mid, the church, hybridmean at
Chorton (examples/buxwv161.py's TUNER, examples/organ.py's room and master).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(cmd, env):
    print("  $ " + " ".join(cmd), flush=True)
    subprocess.check_call(cmd, env=dict(os.environ, **env))


def main(argv):
    pos = []
    skip = False
    for i, a in enumerate(argv[1:], 1):
        if skip:
            skip = False
            continue
        if a.startswith('--'):
            skip = True
            continue
        pos.append(a)
    if len(pos) < 2:
        print(__doc__.strip()); return 2
    score, out = pos
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d   # noqa: E731
    tuner = opt('--tuner', 'hybridmean:466')
    room = opt('--room', 'church')
    env = {'TUNING_ROOM': room, 'TUNING_WET': opt('--wet', '-3'),
           'TUNING_MASTER_DB': opt('--master-db', '-12')}
    layout = opt('--layout', os.path.join(HERE, 'brother_714.yaml'))
    os.makedirs(out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(score))[0]
    dry = os.path.join(out, stem + '.dry.wav')
    objdir = os.path.join(out, 'objects')
    br = os.path.join(ROOT, 'blockrender.py')
    run([sys.executable, br, score, dry, tuner], env)
    run([sys.executable, br, score, dry + '.unused.wav', tuner,
         '--objects', objdir, '--by-source', '--no-reflect'], env)
    run([sys.executable, os.path.join(HERE, 'immersive.py'), objdir, dry, out, layout,
         '--room', room, '--br', opt('--br', '576000'), '--clean'], env)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
