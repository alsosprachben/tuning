#!/usr/bin/env python3
"""Re-cut a sequence's note-offs to match the slurs of its engraved score.

A sequencer's articulation is its own; the composer's is in the score.  This
reads slur arcs from a vector engraving (scorepdf.py) and rewrites note-offs
so that contiguity -- which is what the renderer's legato rule reads -- carries
the engraved phrasing: notes inside a slur run into one another, notes at its
end are released early enough to be heard as separate.

Why bother, when the MIDI already has articulation: because a sequencer's is
usually either absent or invented.  Of the Flight of the Bumblebee sequences
on offer, two encoded the whole piece as one unbroken 1000-note legato and two
broke at random 1-7 note intervals.  IMSLP's orchestral one was far better --
long runs on the bee, detached accompaniment -- but still joined the bee line
in runs of 33, 65 and 81 where Rimsky-Korsakov wrote slurs of 8, 16 and 32.

Two things worth knowing before trusting the output:

  - ALIGNMENT IS THE CHECK.  Slurs are transferred by aligning the engraved
    part against the sequence by pitch.  If that alignment is poor, the
    transfer is meaningless, so the match rate is reported per part; anything
    short of near-total agreement means the staff-to-track mapping is wrong.
  - AN ENGRAVING MAY SLUR ONLY SOME PARTS.  This one slurs the winds and not
    one string part, a common shorthand when the strings double a wind line.
    Taking "no slur" literally there would make the violins spiccato against a
    legato flute, so parts with no engraved slur fall back to the grammar the
    engraved slurs actually use -- bar-aligned groups -- which is stated in
    the output rather than done quietly.

The staff-to-track map is specific to a score's layout and its sequence; MAP
below is for the Bumblebee full score against IMSLP's orchestral MIDI.

Usage:  rearticulate.py SCORE.pdf IN.mid OUT.mid [--transpose N] [--bpm X]
"""
import collections
import sys

import mido

import scorepdf
from scorealign import align

TPB_BAR = 2                      # 2/4
# staff -> (midi track, written->sounding semitones)
MAP = {'Fl':(1,0), 'Ob':(2,0), 'CA':(3,-7), 'Cl1':(4,-3), 'Cl2':(4,-3),
       'Bsn':(5,0), 'Hn1':(6,-7), 'Hn2':(6,-7), 'Tpt':(7,-2),
       'VlnI':(8,0), 'VlnII':(9,0), 'Vla':(10,0), 'Vc':(11,0), 'Db':(12,-12)}
def track_notes(tr):
    """[(onset, pitch, on_index, off_index)] in event order."""
    t = 0; held = collections.defaultdict(list); out = []
    for i, x in enumerate(tr):
        t += x.time
        if x.type == 'note_on' and x.velocity > 0:
            held[x.note].append((t, i))
        elif x.type in ('note_off', 'note_on'):
            q = held.get(x.note)
            if q:
                on, oi = q.pop(0)
                out.append([on, x.note, oi, i, t])
    out.sort(key=lambda v: (v[0], v[1]))
    return out


SHIFT = [0]          # set by rewrite(); the arrangement's own transposition


def transfer(engraved, notes, shift):
    """Slur id per MIDI note, by pitch alignment against the engraving."""
    a = [m + shift for _, _, m, _ in engraved]      # sounding
    b = [p + SHIFT[0] for _, p, _, _, _ in notes]
    if not a or not b: return [None]*len(notes)
    pairs = align(a, b)
    sid = [None]*len(notes)
    ok = 0
    for i, j in pairs:
        if a[i] == b[j]:
            sid[j] = engraved[i][3]; ok += 1
    # a note the aligner skipped, bracketed by one slur, is inside it
    last = None
    for j in range(len(sid)):
        if sid[j] is None and last is not None:
            nxt = next((sid[k] for k in range(j+1, len(sid)) if sid[k] is not None), None)
            if nxt is not None and nxt == last: sid[j] = last
        if sid[j] is not None: last = sid[j]
    return sid, ok, len(pairs)


def bar_groups(notes, tpb, bars=2, maxgap=None):
    """Bar-aligned groups over runs of near-contiguous notes."""
    span = tpb * TPB_BAR * bars
    if maxgap is None: maxgap = tpb // 4 + 1        # a semiquaver
    sid = [None]*len(notes)
    for i in range(len(notes)-1):
        if 0 < notes[i+1][0] - notes[i][0] <= maxgap:
            sid[i] = 'b%d' % (notes[i][0] // span)
            sid[i+1] = 'b%d' % (notes[i+1][0] // span)
    return sid

def rewrite(path_in, path_out, parts, transpose=0, bpm=None, verbose=True):
    SHIFT[0] = transpose
    mid = mido.MidiFile(path_in); tpb = mid.ticks_per_beat
    tol = max(1, tpb // 64)                 # the renderer's contiguity window
    engraved = collections.defaultdict(list)
    for name, rows in parts.items():
        for pg, x, m, s in rows: engraved[name].append((pg, x, m, s))
        engraved[name].sort(key=lambda v: (v[0], v[1]))

    # slur ids per (track, note-in-track)
    per_track = {}
    for name, (trk, shift) in MAP.items():
        if not engraved.get(name): continue
        notes = track_notes(mid.tracks[trk])
        if not notes: continue
        if any(e[3] is not None for e in engraved[name]):
            sid, ok, np = transfer(engraved[name], notes, shift)
            src = "engraved (%d/%d aligned)" % (ok, np)
        else:
            sid, src = bar_groups(notes, tpb), "bar-grid fallback"
        prev = per_track.get(trk)
        if prev is None: per_track[trk] = (notes, sid, src)
        else:
            # two staves share one track (Cl 1&2, Hn 1&2): keep whichever
            # actually carries slurs
            if sum(x is not None for x in sid) > sum(x is not None for x in prev[1]):
                per_track[trk] = (notes, sid, src)

    stats = []
    for trk, (notes, sid, src) in sorted(per_track.items()):
        tr = mid.tracks[trk]
        abs_t = []; t = 0
        for x in tr: t += x.time; abs_t.append(t)
        onsets = sorted(set(n[0] for n in notes))
        nxt = {o: onsets[i+1] for i, o in enumerate(onsets[:-1])}
        joined = cut = 0
        for k, (on, pitch, oi, fi, off) in enumerate(notes):
            no = nxt.get(on)
            if no is None: continue
            same = (k+1 < len(notes) and sid[k] is not None
                    and sid[k+1] == sid[k] and notes[k+1][0] == no)
            if same:
                abs_t[fi] = no; joined += 1
            else:
                gap = max(tol + 8, int(0.18*(no-on)))
                new = min(off, no - gap)
                if new > on: abs_t[fi] = new; cut += (new != off)
        order = sorted(range(len(tr)), key=lambda i: (abs_t[i], 0 if tr[i].type=='note_off'
                       or (tr[i].type=='note_on' and tr[i].velocity==0) else 1))
        ev = []; prev = 0
        for i in order:
            msg = tr[i].copy(time=max(0, abs_t[i]-prev)); prev = abs_t[i]; ev.append(msg)
        mid.tracks[trk] = mido.MidiTrack(ev)
        nm = next((x.name for x in tr if x.type == 'track_name'), '?')
        stats.append((trk, nm, src, joined, cut))

    # Two program changes at the same tick: only the last takes effect, so the
    # file's real intent is the FIRST -- the sequencer appended the second.
    # Left alone, every string part starts on PizzStr and the horns on muted
    # trumpet.  mt32check flags this; it is not audible until it is rendered.
    for tr in mid.tracks:
        seen = {}; drop = []
        t = 0
        for i, x in enumerate(tr):
            t += x.time
            if x.type == 'program_change':
                if (x.channel, t) in seen: drop.append(i)
                else: seen[(x.channel, t)] = i
        for i in reversed(drop):
            if i+1 < len(tr): tr[i+1].time += tr[i].time
            del tr[i]

    # transpose back to the original key, and take the marked tempo
    for tr in mid.tracks:
        for x in tr:
            if x.type in ('note_on','note_off'):
                x.note = max(0, min(127, x.note + transpose))
            elif x.type == 'set_tempo' and bpm:
                x.tempo = int(round(60e6/bpm))
    mid.save(path_out)
    if verbose:
        for trk, name, src, j, c in stats:
            print("  trk%-3d %-20s %-26s joined %4d  detached %4d" % (trk, name, src, j, c))
    return mid


def _cli(argv):
    if len(argv) < 4:
        print(__doc__.strip().splitlines()[-1]); return 2
    pdf, inp, outp = argv[1], argv[2], argv[3]
    tr = int(argv[argv.index('--transpose') + 1]) if '--transpose' in argv else 0
    bpm = float(argv[argv.index('--bpm') + 1]) if '--bpm' in argv else None
    parts, _ = scorepdf.extract(pdf)
    print("== %s + %s -> %s" % (pdf.split('/')[-1], inp.split('/')[-1], outp.split('/')[-1]))
    rewrite(inp, outp, parts, transpose=tr, bpm=bpm)
    return 0


if __name__ == '__main__':
    sys.exit(_cli(sys.argv))
