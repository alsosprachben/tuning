#!/usr/bin/env python3
"""A Hammond through a driven Leslie, and the drive sweep that auditions it.

    python3 examples/hammond.py [outdir]

Builds a short passage on GM 18 (Rock Organ: drawbars out at both ends, rotor
fast, amp pushed) and renders it at four drive settings with NOTHING ELSE
CHANGED. That is the point -- the valve stage is the only variable, so the
progression from clean to breakup to overdrive is the thing being listened to:

    0.0   the signal path with the amplifier out
    1.0   the edge of breakup. The signal peak reaches the grid bias, where a
          3/2-law triode starts to bend; the stage's slope is 0.62 there.
    2.0   into it. Slope 0.43.
    4.0   past it. Slope 0.07 -- this is the clip, and it is the setting the
          old power-series stage could not reach at all, because 1.0 was its
          radius of convergence rather than the amplifier's limit.

WHAT IT MEASURES. Distortion relative to the clean render, over the chords:

    drive 1.0   -24.6 dB     level -28.8 dB
    drive 2.0   -12.5 dB     level -29.5 dB
    drive 4.0    -3.3 dB     level -30.4 dB

The level falling as the drive rises is the compression, and it is not dialled
in: it is the same ceiling that makes the clip.

A SINGLE NOTE DISTORTS NEARLY AS MUCH AS A CHORD -- measured, within 1 dB --
which is worth knowing because it sounds like it should not. The distortion a
Hammond makes is mostly INTERMODULATION rather than harmonics of any one
partial, and intermodulation needs two parents; but a Hammond KEY is already
nine tonewheels, so one key brings its own partners. That is the whole reason a
Hammond thickens through an amplifier where a single sine through the same
amplifier barely would. The passage plays single notes and then chords so the
two can be compared directly.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mido

DRIVES = (0.0, 1.0, 2.0, 4.0)
PROGRAM = 18            # GM 18, Rock Organ -- the one with amp_drive set
TPB = 480


def passage():
    """Single notes first, then chords, so the difference is audible as one.

    A product needs two parents, so a passage that never holds more than one
    note at a time cannot show what this stage does.
    """
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(100), time=0))
    tr.append(mido.Message('program_change', program=PROGRAM, channel=0, time=0))
    # CC1 is the half-moon switch: tremolo, since that is how one is played
    tr.append(mido.Message('control_change', control=1, value=127,
                           channel=0, time=0))

    def bar(groups, beats=1.0):
        for g in groups:
            n = int(TPB * beats)
            for i, p in enumerate(g):
                tr.append(mido.Message('note_on', note=p, velocity=100,
                                       channel=0, time=0))
            for i, p in enumerate(g):
                tr.append(mido.Message('note_off', note=p, velocity=0,
                                       channel=0, time=n if i == 0 else 0))

    # a line, one note at a time -- little to intermodulate with
    bar([[57], [60], [62], [64], [62], [60], [57], [55]], 0.5)
    # the same notes as chords -- the stage has partners now
    bar([[45, 57, 60, 64], [45, 57, 60, 64]], 2.0)
    bar([[43, 55, 59, 62], [43, 55, 59, 62]], 2.0)
    bar([[41, 53, 57, 60], [41, 53, 57, 60]], 2.0)
    bar([[45, 57, 60, 64, 69]], 4.0)
    return m


def main(argv):
    outdir = argv[1] if len(argv) > 1 else '.'
    os.makedirs(outdir, exist_ok=True)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'hammond.mid')
    passage().save(mid)
    print("score: %s" % mid)

    for d in DRIVES:
        out = os.path.join(outdir, 'hammond-drive%g.wav' % d)
        env = dict(os.environ)
        env['TUNING_AMP_DRIVE'] = str(d)
        env.setdefault('TUNING_ROOM', 'chamber')
        env.setdefault('TUNING_MASTER_DB', '-12')
        t0 = time.time()
        r = subprocess.run([sys.executable,
                            os.path.join(root, 'blockrender.py'), mid, out,
                            'even'], env=env, cwd=root,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-3000:]); print(r.stderr[-3000:]); return 1
        amp = [l for l in r.stdout.splitlines() if 'tube amp' in l]
        tot = [l for l in r.stdout.splitlines() if 'blockrender:' in l]
        print("  drive %-4g %5.1fs  %s  %s"
              % (d, time.time() - t0,
                 (amp[0].strip() if amp else 'tube amp: off'),
                 (tot[0].split('->')[0].strip() if tot else '')))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
