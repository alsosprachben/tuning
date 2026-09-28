#!/usr/bin/env python3
"""One score on several tuners, everything else identical -- an A/B by ear.

    python3 examples/temperament_ab.py SCORE.mid OUTDIR [--room chamber] TUNER...

    python3 examples/temperament_ab.py ~/Downloads/contrapunctus1_piano.mid \\
        ~/Downloads/bwx-renders/contrapunctus1_ab hybrid440 hybridmeanpiano stretchedhelmholtz

Each tuner's render is SCORE_<tuner>.mp3. The room, gain and voice are the
same for all, so the tuning is the only variable. A piano's table is valid on
the strings it was projected for: hybridmeanpiano and stretchedhelmholtz are
built on the same Steinway B(f) the grand-piano voice plays with.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import organ


def main(argv):
    args = [a for a in argv[1:]]
    room = 'chamber'
    if '--room' in args:
        i = args.index('--room'); room = args[i + 1]; del args[i:i + 2]
    if len(args) < 3:
        print(__doc__.strip()); return 2
    score, outdir, tuners = args[0], args[1], args[2:]
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(score))[0]
    for tuner in tuners:
        tag = tuner.replace('@', '_').replace(':', '_')
        work = os.path.join(outdir, tag)
        organ.main([argv[0], score, work, '--tuner', tuner, '--room', room])
        shutil.move(os.path.join(work, stem + '.mp3'), os.path.join(outdir, '%s_%s.mp3' % (stem, tag)))
        shutil.rmtree(work)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
