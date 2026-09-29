#!/usr/bin/env python3
"""A fugue from the Well-Tempered Clavier, from the urtext to the piano.

    python3 examples/wtc_fugue.py wtc1f02 [wtc2f12 ...] [--tuner hybridmeanpiano] [--room chamber]
    python3 examples/wtc_fugue.py wtc1f02 --harpsichord          # GM 6, both 8' coupled,
                                                                 # hybridmean at A=415
    python3 examples/wtc_fugue.py wtc2f12 --guitar [--program 29]   # a clean electric guitar
                                                                 # per voice, multi-tracked

The text is the Humdrum edition (github.com/humdrum-tools/bach-wtc, cloned to
~/Downloads/bach-wtc): the Bach-Gesellschaft edition, vol. 14 (1866), encoded
by Walter Hewlett at CCARH. Three steps, each an existing tool:

  1. midgrid kern2midi_ornaments.py: kern to MIDI, ornaments realised Bach's
     way (the trill from above, on the beat), at the file's own *MM tempo --
     CCARH's editorial mark (Fuga 2 of Book 1 ♩=72, Fuga 12 of Book 2 ♩=84).
  2. midgrid perform_baroque.py: expression in TIME -- an ordinary touch, the
     meter breathing, the cadential ritardando. This is notation, not someone's
     performance, so the transform is the right thing to apply.
  3. organ.py's recipe on the grand piano: the room told to both halves.
     hybridmeanpiano -- no wolf anywhere, built on a Steinway's stretched
     octaves -- since these are flat keys the hybrid's wolf would not spare.

Writes ~/Downloads/bwx-renders/wtc/<name>.mp3.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import organ

# WHERE THE FILE'S *MM IS NOT THE TEMPO. Book 2's F minor prelude is marked
# 120 per quarter in 2/4: 70 bars in 70 seconds, a lyrical piece played as a
# study. Performances without the repeats run about 1:45, which is ♩=80.
TEMPO = {'wtc2p12': 80}
# THE SECTIONS THE TEXT MARKS IN WORDS, which kern carries only as comments:
# Book 1's C minor prelude turns Presto at bar 28, has one bar of Adagio (34)
# and ends Allegro (35). (bar, quarter bpm). A kern barline =28 OPENS bar 28 --
# read as closing it, every section came a bar late (Ben: "a measure
# behind"). perform_baroque writes its own timing and ignores tempo in its
# input, so these are applied to its output.
SECTIONS = {'wtc1p02': [(28, 132), (34, 46), (35, 108)]}

MIDGRID = os.path.expanduser('~/repos/midgrid')
KERN = os.path.expanduser('~/Downloads/bach-wtc/kern')
OUT = os.path.expanduser('~/Downloads/bwx-renders/wtc')


def sections(notation, performed, base, marks):
    """Rescale the performed file after each marked bar to that section's tempo.

    Each bar is found in the notation (4/4 bars of quarters) and its first
    note located in the performed file by order -- the performance only moves
    notes, so the nth onset is the same note in both. Time after a mark runs at
    base/bpm of its written speed, the agogic shaping carried along with it."""
    import mido
    nm = mido.MidiFile(notation); pm = mido.MidiFile(performed)
    def onsets(m):
        out = []
        for t in m.tracks:
            a = 0
            for e in t:
                a += e.time
                if e.type == 'note_on' and e.velocity > 0:
                    out.append((a, e.channel, e.note))
        return sorted(out)
    no, po = onsets(nm), onsets(pm)
    if len(no) != len(po):
        raise SystemExit("sections: %d notated onsets against %d performed" % (len(no), len(po)))
    bar_ticks = 4 * nm.ticks_per_beat
    cuts = []                                    # (performed tick, factor from there on)
    for bar, bpm in marks:
        start = (bar - 1) * bar_ticks
        i = next(k for k, o in enumerate(no) if o[0] >= start)
        cuts.append((po[i][0], base / float(bpm)))
    def warp(tick):
        out, prev, f = 0.0, 0, 1.0
        for c, fc in cuts:
            if tick <= c:
                break
            out += (c - prev) * f; prev, f = c, fc
        return int(round(out + (tick - prev) * f))
    for t in pm.tracks:
        a = 0; ab = []
        for e in t:
            a += e.time; ab.append(a)
        last = 0
        for i, e in enumerate(t):
            w = warp(ab[i]); t[i] = e.copy(time=w - last); last = w
    pm.save(performed)
    print("  sections: %s" % ", ".join("bar %d at %d" % m for m in marks))


def main(argv):
    args = argv[1:]
    harpsichord = '--harpsichord' in args
    guitar = '--guitar' in args
    # A FRETTED GUITAR IS EQUAL-TEMPERED by its frets, whatever the piece asks:
    # `even` at A=440. The studio, the amps close-miked.
    gprog = int(args[args.index('--program') + 1]) if '--program' in args else 27
    if guitar:
        os.environ['TUNING_DISTANCE'] = '0.5'
    # A harpsichord's octaves stretch 0.1 cent: the pure-octave hybridmean, at
    # the baroque pitch the instrument stands at.
    tuner = args[args.index('--tuner') + 1] if '--tuner' in args else \
        ('hybridmean:415' if harpsichord else 'even' if guitar else 'hybridmeanpiano')
    room = args[args.index('--room') + 1] if '--room' in args else ('studio' if guitar else 'chamber')
    # Both unisons coupled: the full sound of a fugue without the 4's glitter --
    # one step up from the lone 8', and no further (registration parsimony).
    stops = (args[args.index('--stops') + 1].split(',') if '--stops' in args else ['8', '8-upper'])
    names = [a for a in args if re.match(r'wtc[12][pf]\d\d$', a)]
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        krn = os.path.join(KERN, name + '.krn')
        mm = re.search(r'^\*MM(\d+)', open(krn).read(), re.M)
        bpm = TEMPO.get(name) or (int(mm.group(1)) if mm else 72)
        raw = os.path.join(OUT, name + '.notation.mid')
        subprocess.run([sys.executable, os.path.join(MIDGRID, 'kern2midi_ornaments.py'), krn, raw, str(bpm)],
                       check=True)
        tag = name + ('_harpsichord' if harpsichord else '_guitar' if guitar else '')
        perf = os.path.join(OUT, tag + '.mid')
        subprocess.run([sys.executable, os.path.join(MIDGRID, 'skills/baroque-agogics/examples/perform_baroque.py'),
                        raw, perf, '--bpm', str(bpm)], check=True)
        if name in SECTIONS:
            sections(raw, perf, bpm, SECTIONS[name])
        if harpsichord:
            import mido
            import lib
            m = mido.MidiFile(perf)
            chans = sorted({e.channel for t in m.tracks for e in t if e.type == 'note_on'})
            for t in m.tracks:
                for i, e in enumerate(t):
                    if e.type == 'program_change':
                        t[i] = e.copy(program=6)
            for ch in chans:               # a program change where the file has none
                if not any(e.type == 'program_change' and e.channel == ch for t in m.tracks for e in t):
                    m.tracks[-1].insert(0, mido.Message('program_change', channel=ch, program=6))
            m.save(perf)
            lib.set_stops(perf, perf, {ch: stops for ch in chans})
        if guitar:
            # ONE GUITAR PER VOICE, as a guitarist records a fugue: the bass voice
            # centre (in drop C -- it goes to C2, 14 notes under a standard low
            # E), the alto left, the soprano right.
            import mido
            m = mido.MidiFile(perf)
            chans = sorted({e.channel for t in m.tracks for e in t if e.type == 'note_on'})
            pan = {0: 64, 1: 36, 2: 92, 3: 92}
            for t in m.tracks:
                for i, e in enumerate(t):
                    if e.type == 'program_change':
                        t[i] = e.copy(program=gprog)
            head = m.tracks[-1]
            for ch in chans:
                if not any(e.type == 'program_change' and e.channel == ch for t in m.tracks for e in t):
                    head.insert(0, mido.Message('program_change', channel=ch, program=gprog))
                head.insert(0, mido.Message('control_change', channel=ch, control=10, value=pan.get(ch, 64)))
            m.save(perf)
        organ.main([argv[0], perf, OUT, '--tuner', tuner, '--room', room])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
