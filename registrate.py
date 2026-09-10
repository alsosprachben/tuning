#!/usr/bin/env python3
"""Put a score's registration onto a performance of it.

A recorded performance carries the playing and nothing else: the Sankey Bach
corpus is 135 files with zero controller events, so no stop is ever drawn. An
engraving carries the registration -- Bach's forte and piano marks in the
Italian Concerto ARE manual changes, since a harpsichord has no touch dynamics
-- and carries the hands, on separate staves, but its timing is dead.

This takes the registration and the hand separation from the score and puts them
on the performance's own timing, note by note, through an alignment.

The engraving is expected to come from LilyPond with `\\midi`, where each staff
is a track and the dynamics arrive as velocities. Mutopia's own MIDI ships flat
at velocity 90 -- their export drops the marks -- so render the .ly yourself.

WHY THE STAFF COMES FROM PITCH-AT-TIME, NOT FROM THE ALIGNMENT. The first
version took each note's staff from whichever score note the alignment paired it
with. Inside a chord the pairing can pick the wrong member, and it put one A#4
on the upper staff and its own immediate repeat on the lower -- which is audible
twice over: the hands carry different stops in the Presto, so alternate notes
changed timbre, and the renderer's one-string-per-(channel, pitch) rule stopped
matching, so repeated notes overlapped themselves. Ben heard it as "every other
having their attack/release squashed". Looking the pitch up in the score at that
moment is robust to both.

Usage: registrate.py PERF.mid OUT.mid SCORE.mid [SCORE2.mid ...]
         [--forte N] [--piano N] [--gap S]

One SCORE per movement, in order; the performance is split at its own silences.
--forte/--piano are CC11 stop masks (bit 0 = 8' lower, 1 = 8' upper, 2 = 4',
3 = lute), defaulting to 7 (grand jeu) and 2 (the upper manual's single 8').
"""
import bisect
import os
import sys

import mido

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from scorealign import align, note_stream
import blockrender

TPB = 960


def movement_spans(notes, n, gap=2.0):
    """Split a performance into n spans at its longest silences."""
    ev = sorted((on, off) for ch, note, on, off, v, r, p in notes)
    end = max(f for o, f in ev)
    quiet = []
    cur = 0.0
    for o, f in ev:
        if o > cur + gap:
            quiet.append((cur, o))
        cur = max(cur, f)
    quiet.sort(key=lambda q: q[0] - q[1])          # longest first
    cuts = sorted((a + b) / 2 for a, b in quiet[:max(0, n - 1)])
    edges = [0.0] + cuts + [end + 1.0]
    return list(zip(edges, edges[1:]))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    def opt(name, d):
        return type(d)(argv[argv.index(name) + 1]) if name in argv else d
    if len(args) < 3:
        print(__doc__[__doc__.index("Usage:"):].rstrip())
        return 2
    perf, outp, scores = args[0], args[1], args[2:]
    F, P, gap = opt('--forte', 7), opt('--piano', 2), opt('--gap', 2.0)

    _cp, _cps, notes, ccs, _t, _lg = blockrender.parse(perf)
    played = sorted((on, off, n) for ch, n, on, off, v, r, pg in notes)
    spans = movement_spans(notes, len(scores), gap)
    spt = 0.5 / TPB
    ev = []
    total = matched = 0
    for score, (lo, hi) in zip(scores, spans):
        A = note_stream(score)
        B = [p for p in played if lo <= p[0] < hi]
        pairs = align([x[1] for x in A], [x[2] for x in B])
        px = [B[j][0] for i, j in pairs]
        py = [A[i][0] for i, j in pairs]
        # Every score note this pitch ever appears at, so a staff can be looked
        # up by PITCH AT TIME rather than by the alignment's exact pairing.
        bypitch = {}
        for st, n, si, v in A:
            bypitch.setdefault(n, []).append((st, si, v))
        cur = {}
        last = 0
        for on, off, n in B:
            total += 1
            st = py[min(bisect.bisect_left(px, on), len(px) - 1)] if px else on
            cand = bypitch.get(n)
            if cand:
                j = min(range(len(cand)), key=lambda q: abs(cand[q][0] - st))
                staff, vel = cand[j][1], cand[j][2]
                matched += 1
            else:
                staff, vel = last, None       # an ornament: it stays in its hand
            last = staff
            want = P if (vel is not None and vel < 80) else \
                   (F if (vel is not None and vel >= 93) else cur.get(staff))
            if want is not None and want != cur.get(staff):
                ev.append((int(on / spt) - 1,
                           mido.Message('control_change', control=11, value=want,
                                        channel=staff)))
                cur[staff] = want
            ev.append((int(on / spt),
                       mido.Message('note_on', note=n, velocity=96, channel=staff)))
            ev.append((int(off / spt),
                       mido.Message('note_off', note=n, velocity=0, channel=staff)))
    prog = sorted({x.channel for _, x in ev if x.type == 'note_on'})
    head = [(0, mido.MetaMessage('set_tempo', tempo=500000))]
    head += [(0, mido.Message('program_change', program=6, channel=c)) for c in prog]
    ev = head + sorted(ev, key=lambda p: (p[0], 0 if p[1].type != 'note_on' else 1))
    out = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); out.tracks.append(tr)
    prev = 0
    for at, x in ev:
        x.time = max(0, at - prev); prev = max(prev, at); tr.append(x)
    out.save(outp)
    cc = sum(1 for _, x in ev if x.type == 'control_change')
    print("  %d movements, %d notes (%d placed by the score, %d ornaments kept in hand)"
          % (len(scores), total, matched, total - matched))
    print("  %d registration changes on the performance's own timing -> %s" % (cc, outp))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
