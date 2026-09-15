#!/usr/bin/env python3
"""Render a choral movement: voices through the tract, everything else not.

    python3 examples/choral.py SCORE [outdir] [--choir-only] [--both] [--lang latin]

SCORE is a MIDI or MusicXML with lyrics in it. The choir is found by having
notes AND lyrics, which is the only reliable test: engravings carry empty
staves named Soprano beside the real ones (Mozart's Lacrimosa export has four
of each), and they carry lyrics on separate track with no notes at all (the
Dies Irae export does, one per voice). Neither is a part.

Two renders, because they cannot be one. singpass.py is a source-filter pass
and filters the WHOLE file, so an orchestra sent through it is played inside a
singer's mouth. The voices go through the tract, everything else goes straight
through blockrender, and the two are put back together.

The room is what makes that reassembly delicate. blockrender computes only
first-order images and writes a .room.json saying what the piece fed the hall
per band; the diffuse tail is roomtail's convolution over the sum. So the
stems are summed DRY and given the hall ONCE, with their sidecars merged --
a choir and a string section do not feed a room alike, and a mix that
inherits whichever sidecar it found first gets the wrong one.

Levels are not balanced by hand WHEN THE SCORE HAS ANY. Both stems come off
the same file at the same settings, so summing at unit gain keeps whatever was
notated -- but check that something was. The Dies Irae export gives every choir
note velocity 95 and every first violin 101, one flat value per staff, which is
LilyPond's default and not Mozart's marking. Summed at unit gain that buries
the choir 6 dB under the orchestra where the two play together, and calls an
exporter's default a balance. --choir-db states the correction out loud.
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
    choir_only = '--choir-only' in argv
    both = '--both' in argv
    lang = argv[argv.index('--lang') + 1] if '--lang' in argv else 'latin'
    choir_db = float(argv[argv.index('--choir-db') + 1]) if '--choir-db' in argv else 0.0
    stem = os.path.splitext(os.path.basename(score))[0]
    os.makedirs(outdir, exist_ok=True)

    midi = lib.from_musicxml(score) if score.lower().endswith(
        ('.mxl', '.xml', '.musicxml')) else score
    dyn = lib.has_dynamics(midi)
    for t in lib.describe(midi):
        d = dyn.get(t['i'])
        print("  %2d %-30s notes=%-4d lyrics=%-4d ch=%-6s %s"
              % (t['i'], t['name'], t['notes'], t['lyrics'], t['channels'],
                 '' if d is None else ('dynamics' if d[0] else 'vel %s' % d[1])))

    keep = lib.choir_tracks(midi)
    if not keep:
        print("  no track carries both notes and lyrics -- wrong score?")
        return 1
    rest = lib.other_tracks(midi, set(keep))
    print("  choir: tracks %s" % keep)
    print("  rest:  tracks %s" % (rest or 'none'))

    choir = lib.take_tracks(midi, os.path.join(outdir, stem + '.choir.mid'), keep)
    for name, tube in [('tube', True)] + ([('formant', False)] if both else []):
        wav = os.path.join(outdir, '%s.choir.%s.wav' % (stem, name))
        if not os.path.exists(wav):
            lib.sing(choir, wav, lang=lang, tube=tube,
                     dry=bool(rest) and not choir_only)
        if choir_only or not rest:
            print("  %-8s -> %s" % (name, lib.mp3(wav)))
            continue

        omid = lib.take_tracks(midi, os.path.join(outdir, stem + '.rest.mid'), rest)
        owav = os.path.join(outdir, stem + '.rest.wav')
        if not os.path.exists(owav):
            lib.render_plain(omid, owav)

        bal, frac = lib.overlap_balance(wav, owav)
        print("  choir sings %.0f%% of it, and sits %+.1f dB on the rest there"
              % (100 * frac, bal))
        dry = os.path.join(outdir, '%s.full.%s.dry.wav' % (stem, name))
        lib.sum_wavs([wav, owav], dry, gains=[10.0 ** (choir_db / 20.0), 1.0])
        if choir_db:
            print("  applied --choir-db %+.1f -> %+.1f dB"
                  % (choir_db, bal + choir_db))
        lib.merge_room([os.path.splitext(wav)[0] + '.room.json',
                        os.path.splitext(owav)[0] + '.room.json'],
                       os.path.splitext(dry)[0] + '.room.json')
        wet = os.path.join(outdir, '%s.full.%s.wav' % (stem, name))
        lib.roomtail(dry, wet)
        print("  %-8s -> %s" % (name, lib.mp3(wet)))
        for lo, hi, db in lib.bands(wet):
            print("      %5d-%5d Hz  %+6.1f dB" % (lo, hi, db))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
