#!/usr/bin/env python3
"""Decode an engraved score (vector PDF) to pitches and slurs.

The staff lines give an exact pitch grid, so pitch is arithmetic: a notehead's
y, divided by the line spacing, is a diatonic step.  Accidentals are glyphs a
little to the left at the same height, scoped to the bar.  Slurs are beziers,
and a note is inside one when its x lies between the curve's endpoints.

Everything here is checkable, and should be checked.  The intended use is to
align the decoded part against an independent sequence of the same music: a
misread grid shows up at once as a systematic interval error, where OMR would
hand back plausible nonsense.  On Rimsky-Korsakov's "Flight of the Bumblebee"
the flute decoded to 543 notes that aligned against an unrelated MIDI of the
same music with zero pitch mismatches.

Two traps, both of which produced wrong answers before they were fixed:

  - Grouping staff lines by proximity merges a stray wide rule (a hairpin, an
    8va bracket) into its neighbour, and then every instrument on the page is
    assigned to the wrong staff.  A staff is five lines at EQUAL spacing.
  - A stem looks like a barline if you only ask whether a vertical segment
    touches the staff.  A barline spans it; a stem reaches part way in.  Get
    this wrong and accidentals reset mid-bar.

Usage:  scorepdf.py SCORE.pdf [--staves N] [--part NAME]
"""
import collections
import json
import re
import sys

import pdfmus

HEADS   = {9, 20}                  # filled, open
ACC     = {5: 1, 10: 0, 6: -1}     # sharp, natural, flat
CLEFS   = {3: 'treble', 7: 'bass', 8: 'c'}
LETTER  = [0, 2, 4, 5, 7, 9, 11]   # C D E F G A B

# diatonic index (7*octave + degree) of the staff's BOTTOM line
BOTTOM  = {'treble': 4*7+2,        # E4
           'bass':   2*7+4,        # G2
           'c':      3*7+3}        # F3  (alto C clef: middle line C4)


def staves(lines):
    hor = [(round(y1,1), min(x1,x2), max(x1,x2))
           for x1,y1,x2,y2 in lines if abs(y1-y2) < 0.5]
    wide = sorted(set(h[0] for h in hor if h[2]-h[1] > 200))
    # A staff is five lines at EQUAL spacing.  Grouping by proximity alone
    # merges a stray wide rule (a hairpin, an 8va bracket) into its
    # neighbouring staff, which then shifts every instrument on the page.
    out, i = [], 0
    while i + 4 < len(wide):
        win = wide[i:i+5]
        gaps = [b-a for a, b in zip(win, win[1:])]
        if max(gaps) - min(gaps) < 0.6 and 3.0 < sum(gaps)/4 < 5.0:
            out.append(win); i += 5
        else:
            i += 1
    return out


def barlines(lines, ylow, yhigh):
    """A barline spans the whole staff; a stem reaches only part way in."""
    xs = set()
    for x1,y1,x2,y2 in lines:
        if abs(x1-x2) < 0.8 and min(y1,y2) <= ylow+1 and max(y1,y2) >= yhigh-1:
            xs.add(round(x1,1))
    return sorted(xs)


def staff_glyphs(glyphs, st):
    step = (st[-1]-st[0])/8.0
    lo, hi = st[0]-7*step, st[-1]+9*step
    return [g for g in glyphs if g[0]=='R20' and lo < g[3] < hi]


def clef_of(g):
    for f,sz,x,y,code in sorted(g, key=lambda v: v[2]):
        if code in CLEFS: return CLEFS[code]
    return 'treble'


def decode_staff(glyphs, lines, st, clef=None):
    """-> [(x, midi)] in written pitch, accidentals scoped to the bar."""
    g = staff_glyphs(glyphs, st)
    if clef is None: clef = clef_of(g)
    bot, step = st[0], (st[-1]-st[0])/8.0
    base = BOTTOM[clef]
    heads = sorted([v for v in g if v[4] in HEADS], key=lambda v: v[2])
    accs  = sorted([v for v in g if isinstance(v[4],int) and v[4] in ACC],
                   key=lambda v: v[2])
    bars = barlines(lines, st[0], st[-1])
    out, state, bi = [], {}, 0
    for hx, hy in [(h[2], h[3]) for h in heads]:
        while bi < len(bars) and bars[bi] < hx - 1.0:
            state = {}; bi += 1
        dia = base + int(round((hy-bot)/step))
        alt = None
        for a in accs:
            if 0 < hx - a[2] < 12 and abs(a[3]-hy) < step*0.6:
                alt = ACC[a[4]]
        if alt is not None: state[dia] = alt
        out.append((hx, 12*(dia//7) + LETTER[dia%7] + state.get(dia,0) + 12))
    return out

NUM   = r'([\d.\-]+)'
MOVE  = re.compile((r'%s\s+%s\s+m\s+' % (NUM, NUM)).encode())
CURVE = re.compile((r'%s\s+%s\s+%s\s+%s\s+%s\s+%s\s+c' % ((NUM,)*6)).encode())


def raw_arcs(content, scale=0.12):
    """Every bezier path: (x0, y0, x1, y1, apex_y), in page units."""
    out = []
    for m in MOVE.finditer(content):
        x0, y0 = float(m.group(1)), float(m.group(2))
        tail = content[m.end():m.end()+220]
        c = CURVE.match(tail)
        if not c: continue
        v = [float(g) for g in c.groups()]
        out.append((x0*scale, y0*scale, v[4]*scale, v[5]*scale,
                    max(v[1], v[3])*scale))
    return out


def slurs(content, scale=0.12, minlen=4.0):
    """Merged slur arcs, longest first, duplicates removed."""
    arcs = [a for a in raw_arcs(content, scale) if a[2]-a[0] >= minlen]
    arcs.sort(key=lambda a: (a[0], -(a[2]-a[0])))
    out = []
    for a in arcs:
        dup = False
        for b in out:
            if abs(a[0]-b[0]) < 3 and abs(a[2]-b[2]) < 3 and abs(a[1]-b[1]) < 4:
                dup = True; break
        if not dup: out.append(a)
    return out

NAMES = ['Db','Vc','Vla','VlnII','VlnI','Timp','Tba','Tbn','Tpt',
         'Hn2','Hn1','Bsn','Cl2','Cl1','CA','Ob','Fl']          # bottom -> top

def assign_staff(y, staves):
    """Nearest staff, measured to the staff's band rather than its centre."""
    best, bd = None, 1e9
    for i, st in enumerate(staves):
        step = (st[-1]-st[0])/8.0
        lo, hi = st[0]-9*step, st[-1]+11*step
        d = 0.0 if lo <= y <= hi else min(abs(y-lo), abs(y-hi))
        if d < bd: best, bd = i, d
    return best, bd

def extract(pdf='score.pdf'):
    P = pdfmus.pages(pdf)
    parts = {n: [] for n in NAMES}          # (page, x, midi, slur_id)
    nslur = collections.Counter()
    gid = 0
    for pi, c in enumerate(P):
        g, l = pdfmus.run(c)
        st = staves(l)
        if len(st) != 17:
            raise SystemExit("page %d: %d staves" % (pi+1, len(st)))
        notes = {i: decode_staff(g, l, s) for i, s in enumerate(st)}
        marks = {i: {} for i in range(17)}
        for x0, y0, x1, y1, apex in slurs(c):
            if x1 - x0 < 4: continue
            si, d = assign_staff((y0+y1)/2.0, st)
            if si is None or d > 8: continue
            gid += 1; nslur[NAMES[si]] += 1
            for j, (nx, nm) in enumerate(notes[si]):
                if x0-6 <= nx <= x1+6: marks[si][j] = gid
        for i, seq in notes.items():
            for j, (nx, nm) in enumerate(seq):
                parts[NAMES[i]].append((pi, nx, nm, marks[i].get(j)))
    return parts, nslur


def _cli(argv):
    pdf = argv[1] if len(argv) > 1 else None
    if not pdf:
        print(__doc__.strip().splitlines()[-1]); return 2
    want = argv[argv.index('--part') + 1] if '--part' in argv else None
    parts, ns = extract(pdf)
    for n in NAMES[::-1]:
        if want and n != want: continue
        v = parts[n]
        sl = sum(1 for e in v if e[3] is not None)
        print("  %-6s %4d notes  %3d slurs  %4d slurred (%.0f%%)"
              % (n, len(v), ns[n], sl, 100 * sl / max(1, len(v))))
    return 0


if __name__ == '__main__':
    sys.exit(_cli(sys.argv))
