#!/usr/bin/env python3
"""Pulling out all the stops: BuxWV 161's ending on every stop the console has,
after the same passage as registered -- an A/B at one gain.

    python3 examples/organ_tutti.py OUTDIR [--from 272] [--approved APPROVED.wav]

Every rank of GM 19's stop word, 16' and 32' to the tierce, reeds, mixture,
celeste and vox humana, on the manual and the pedal, except the tremulant:
no organist draws it in a full organ, and it is a wind valve, not a rank. The
reed channels (2, 3) double the manual's and the pedal's notes, so they are
dropped: with every rank on both, a reed channel would only sound each rank
twice.

The score is the fixed-pedal performed MIDI (examples/buxwv161.py; the pedal at
its written pitch), the room and tuner buxwv161.py's. The A/B is cut from the
two renders' wet files at the same time and the same gain, then normalised
together, so the tutti is as much louder as it really is. --approved defaults
to the newranks render Ben approved.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib                                             # noqa: E402
import organ                                           # noqa: E402
import tonelib as T                                    # noqa: E402

DL = os.path.expanduser("~/Downloads/organ")
PERFORMED = os.path.join(DL, "buxwv161_newranks_pedal8", "buxwv161_performed.mid")
APPROVED = os.path.join(DL, "buxwv161_newranks_pedal8", "buxwv161_graded.wav")
TUNER = 'hybridmean:466'


def main(argv):
    pos = [a for i, a in enumerate(argv[1:], 1) if not a.startswith('--')
           and argv[i - 1] not in ('--from', '--approved')]
    out = pos[0] if pos else os.path.join(DL, "buxwv161_tutti")
    start = float(argv[argv.index('--from') + 1]) if '--from' in argv else 272.0
    approved = argv[argv.index('--approved') + 1] if '--approved' in argv else APPROVED
    os.makedirs(out, exist_ok=True)
    every = [r[0] for r in T.FlueOrganProperties.stop_ranks if r[0] != 'tremulant']
    print("  %d stops: %s" % (len(every), ", ".join(every)))
    tutti = os.path.join(out, 'buxwv161_tutti.mid')
    lib.set_stops(PERFORMED, tutti, {0: every, 1: every, 2: [], 3: []})
    organ.main([argv[0], tutti, out, '--tuner', TUNER])
    wet = os.path.join(out, 'buxwv161_tutti.wav')

    # the A/B: registered, a breath, all the stops -- one gain for both
    a, b = os.path.join(out, 'ab_a.wav'), os.path.join(out, 'ab_b.wav')
    subprocess.check_call(['sox', approved, a, 'trim', str(start), 'pad', '0', '2'])
    subprocess.check_call(['sox', wet, b, 'trim', str(start)])
    ab = os.path.join(out, 'buxwv161_registered_then_allstops.wav')
    subprocess.check_call(['sox', a, b, ab, 'gain', '-n', '-1'])
    mp3 = lib.mp3(ab)
    for f in (a, b):
        os.remove(f)
    print("  -> %s" % mp3)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
