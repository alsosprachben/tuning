#!/usr/bin/env python3
"""Mozart, Requiem K.626, Lacrimosa -- the choir alone, with the Latin text.

    python3 examples/lacrimosa_choir.py SCORE.mxl [outdir] [--both]

The score is an SATB reduction in MusicXML; supply your own (this one came
from a MuseScore export of the Requiem and is not redistributed here). The
engraving carries thirteen tracks: four EMPTY staves named Treble/Alto/Tenor/
Bass, four string parts, and four more named Soprano/Alto/Tenor/Bass that hold
the notes and the lyrics. Selecting by name gets the empty ones, so the choir
is found by having notes AND lyrics.

With --both it renders the same choir twice -- once through the three-pole
formant filter, once through the Kelly-Lochbaum tube (vocaltube.py) -- from
one source render, so the only difference between the two files is the tract.

With --orchestra the strings come too. They CANNOT go through singpass: that
pass filters the whole file, so an orchestra sent through it is played inside
a singer's mouth. Voices and orchestra are rendered separately and dry, summed,
and given the hall once over the pair -- which needs their two room sidecars
merged, because a choir and a string section do not feed a room alike and
whichever sidecar the mix happened to inherit would be the wrong one.
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
    both = '--both' in argv
    orch = '--orchestra' in argv
    os.makedirs(outdir, exist_ok=True)

    midi = lib.from_musicxml(score) if score.lower().endswith(
        ('.mxl', '.xml', '.musicxml')) else score

    for t in lib.describe(midi):
        print("  %2d %-28s notes=%-4d lyrics=%-4d ch=%s" %
              (t['i'], t['name'], t['notes'], t['lyrics'], t['channels']))
    keep = lib.choir_tracks(midi)
    if not keep:
        print("  no track carries both notes and lyrics -- is this the right score?")
        return 1
    print("  choir: tracks %s" % keep)

    choir = lib.take_tracks(midi, os.path.join(outdir, 'lacrimosa_choir.mid'), keep)

    jobs = [('tube', True)] + ([('formant', False)] if both else [])
    for name, tube in jobs:
        wav = os.path.join(outdir, 'lacrimosa_choir_%s.wav' % name)
        lib.sing(choir, wav, lang='latin', tube=tube, dry=orch)
        if not orch:
            out = lib.mp3(wav)
            print("  %-8s -> %s" % (name, out))
            for lo, hi, db in lib.bands(wav):
                print("      %5d-%5d Hz  %+6.1f dB" % (lo, hi, db))
            continue

        rest = lib.other_tracks(midi, set(keep))
        print("  orchestra: tracks %s" % rest)
        omid = lib.take_tracks(midi, os.path.join(outdir, 'lacrimosa_orch.mid'),
                               rest)
        owav = os.path.join(outdir, 'lacrimosa_orch.wav')
        lib.render_plain(omid, owav)

        mix = os.path.join(outdir, 'lacrimosa_full_%s.dry.wav' % name)
        lib.sum_wavs([wav, owav], mix)
        lib.merge_room([os.path.splitext(wav)[0] + '.room.json',
                        os.path.splitext(owav)[0] + '.room.json'],
                       os.path.splitext(mix)[0] + '.room.json')
        wet = os.path.join(outdir, 'lacrimosa_full_%s.wav' % name)
        lib.roomtail(mix, wet)
        out = lib.mp3(wet)
        print("  %-8s -> %s" % (name, out))
        for lo, hi, db in lib.bands(wet):
            print("      %5d-%5d Hz  %+6.1f dB" % (lo, hi, db))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
