#!/usr/bin/env python3
"""Render a registered organ score, the way BWV 542 v7 was rendered.

    python3 examples/organ.py SCORE.mid [outdir] [--tuner hybrid] [--room church]

The recipe, which until now lived only in a shell line and had to be dug back
out of a transcript:

    TUNING_ROOM=church TUNING_TUNER=hybrid TUNING_MASTER_DB=-12  blockrender
    TUNING_ROOM=church                                           roomtail

Every part of that is a decision, so they are written down here rather than
passed as flags nobody will remember.

  church   an organ is not in a chamber. blockrender computes first-order
           images against the room it is told about, and roomtail convolves
           the diffuse tail from the SAME room -- so both have to be told, and
           told the same thing. Setting it for one and not the other gives a
           hall's early reflections with a studio's tail.

  hybrid   verified by ear as the baroque tuner, and at A=415, which is the
           pitch that goes with it. `hybrid440` is the same temperament at
           concert pitch and is the general default now -- but this recipe is
           Bach on an organ, so it stays at baroque pitch deliberately.
           NOT hybridharm, which tracks
           the second harmonic; BWV 542 was rendered with both at different
           times and hybrid is the one that stuck.

  -12 dB   headroom for the tail. roomtail ADDS energy, so a mix that peaks
           near full scale dry has nowhere to put its room.

The score must already be REGISTERED -- stops chosen, ranks on their own
channels, CC43 selecting and CC11 shaping. registrate.py does that; this does
not, because registration is a musical decision per piece and per instrument.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip()); return 2
    score = argv[1]
    outdir = argv[2] if len(argv) > 2 and not argv[2].startswith('--') else '.'
    tuner = argv[argv.index('--tuner') + 1] if '--tuner' in argv else 'hybrid'
    room = argv[argv.index('--room') + 1] if '--room' in argv else 'church'
    master = argv[argv.index('--master-db') + 1] if '--master-db' in argv else '-12'
    stem = os.path.splitext(os.path.basename(score))[0]
    os.makedirs(outdir, exist_ok=True)

    for t in lib.describe(score):
        if t['notes']:
            print("  %2d %-22s notes=%-5d ch=%s prog=%s"
                  % (t['i'], t['name'], t['notes'], t['channels'], t['programs']))

    dry = os.path.join(outdir, stem + '.dry.wav')
    lib.render_plain(score, dry, tuner=tuner,
                     extra_env={'TUNING_ROOM': room,
                                'TUNING_MASTER_DB': str(master)})
    wet = os.path.join(outdir, stem + '.wav')
    lib.roomtail(dry, wet, env={'TUNING_ROOM': room})
    out = lib.mp3(wet)
    print("  %s tuner, %s room -> %s" % (tuner, room, out))
    for lo, hi, db in lib.bands(wet):
        print("      %5d-%5d Hz  %+6.1f dB" % (lo, hi, db))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
