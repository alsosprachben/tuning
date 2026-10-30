"""The emitter's one-item cells as named attributes: `_MCH[0]` in _prepare
becomes `em.channel`, `self._MCH[0]` in _Emitter becomes `self.channel`,
and `_MCH = [0]` becomes `em.channel = 0`.

    python3 examples/refactor/prep_cells.py [--dry]

A cell was how a closure shared a value it could rebind: a one-item list
both sides index. With the emitter an object, an attribute does that
directly, and says what it is. Only a cell used NOWHERE but as X[0] --
never sliced, passed whole to a pass, or rebound -- is converted (checked
here; _EFXN and _DAMP_OPEN are handed whole to other code and stay). em is
made at the top of _prepare, before the first cell is bound.

Run examples/prepident.py after: the tables must not move.
"""
import ast
import io
import os
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'blockrender.py')

# cell -> attribute, named from the comment at its binding
NAMES = {
    '_S0': 'stream_row0',       # the note being emitted: its first row (streamed only)
    '_BR': 'bend_row',          # per-note bend row, -1 = this note does not bend
    '_VDL': 'vibrato_delay',    # per-note vibrato delay, seconds (CC78)
    '_PJ': 'jitter_scale',      # per-note pitch-jitter frequency scale
    '_XPON': 'transposed',      # this note is transposed whole
    '_PL': 'player',            # which player of a section this partial belongs to
    '_FX': 'moog_filter_row',   # the Moog filter row of this note, -1 = none
    '_MK': 'moog_key',          # a Moog partial's oscillator * 4096 + harmonic
    '_NOREFL': 'no_reflections',  # emit no room images for this partial
    '_LATE': 'late_copy',       # rows of a late copy (bloom)
    '_RINGF': 'ring_rows',      # emitting ring rows
    '_RD': 'image_delay',       # a room image's extra path, in samples
    '_FMW': 'fm_omega',         # 1 -> 2 FM: OSC 1's angular frequency
    '_FMPH': 'fm_phase',        # ...and its phase
    '_GSD_OPEN': 'gs_delay_open',   # this note's (first row, send) for the GS delay
    '_PAR_OPEN': 'parallel_open',   # a parallel EFX type's note
    '_MCH': 'channel',          # MIDI channel of the note being emitted
    '_LV': 'fader_row',         # its channel's fader row, if the fader moves
    '_PX': 'pos_x',             # metres, + = right
    '_PZ': 'pos_z',             # metres, + = up
    '_AZ': 'azimuth',
    '_radius': 'radius',        # radiating aperture for this partial
    '_REV': 'reverse',          # played backwards: (onset, arrival)
    '_REG_OPEN': 'register_open',   # the free-string strike being emitted
    '_HT_PEND': 'htrem_pending',
    '_ON_NOW': 'onset',         # the onset, seconds, of the note being emitted
    '_SND_PEND': 'sound_pending',
    '_PUSH_PEND': 'push_pending',
    '_FOLD': 'fold',            # re-strike of a still-ringing plate
    '_FOLDIN': 'fold_in',       # what the strike before left this one to take in
    '_HAM': 'hammer_on',        # seconds since the pick, if a hammer-on
    '_NOTE_END': 'note_end',    # the last note's rows end here
}


def main(argv):
    src = open(SRC).read()
    t = ast.parse(src)
    prep = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare')
    cls = next(n for n in t.body if isinstance(n, ast.ClassDef) and n.name == '_Emitter')
    parent = {}
    for n in ast.walk(t):
        for c in ast.iter_child_nodes(n):
            parent[c] = n
    zero = lambda p: isinstance(p, ast.Subscript) and isinstance(p.slice, ast.Constant) and p.slice.value == 0

    binds, handovers, bad = {}, {}, []
    for s in ast.walk(prep):
        if isinstance(s, ast.Assign) and len(s.targets) == 1:
            tg = s.targets[0]
            if isinstance(tg, ast.Name) and tg.id in NAMES:
                if not (isinstance(s.value, ast.List) and len(s.value.elts) == 1) or tg.id in binds:
                    bad.append('%s bound at %d not as one fresh [v]' % (tg.id, s.lineno))
                binds[tg.id] = s
            elif (isinstance(tg, ast.Attribute) and isinstance(tg.value, ast.Name) and tg.value.id == 'em'
                  and isinstance(s.value, ast.Name) and s.value.id in NAMES and tg.attr == s.value.id):
                handovers[s.value.id] = s
    edits = []          # (row, col_start, col_end, text)
    for n in ast.walk(t):
        if isinstance(n, ast.Name) and n.id in NAMES:
            p = parent[n]
            inside_prep = prep.lineno <= n.lineno <= prep.end_lineno
            if zero(p) and p.value is n and inside_prep:
                if p.lineno != p.end_lineno:
                    bad.append('%s[0] split over lines at %d' % (n.id, p.lineno))
                edits.append((p.lineno, p.col_offset, p.end_col_offset, 'em.' + NAMES[n.id]))
            elif binds.get(n.id) is not None and p is binds[n.id]:
                pass
            elif handovers.get(n.id) is not None and p is handovers[n.id]:
                pass
            else:
                bad.append('%s used as %s at %d' % (n.id, type(p).__name__, n.lineno))
        elif (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self'
              and n.attr in NAMES):
            p = parent[n]
            if not (cls.lineno <= n.lineno <= cls.end_lineno):
                bad.append('self.%s outside _Emitter at %d' % (n.attr, n.lineno))
            elif zero(p) and p.value is n and p.lineno == p.end_lineno:
                edits.append((p.lineno, p.col_offset, p.end_col_offset, 'self.' + NAMES[n.attr]))
            else:
                bad.append('self.%s used as %s at %d' % (n.attr, type(p).__name__, n.lineno))
        elif (isinstance(n, ast.Attribute) and n.attr in set(NAMES.values()) and isinstance(n.value, ast.Name)
              and (n.value.id == 'em' or (n.value.id == 'self' and cls.lineno <= n.lineno <= cls.end_lineno))):
            bad.append('emitter attribute %s already in use at %d' % (n.attr, n.lineno))
    missing = sorted(set(NAMES) - set(binds))
    if missing:
        bad.append('no binding found for %s' % missing)
    print('cells: %d; %d uses rewritten; %d bindings; %d hand-overs dropped'
          % (len(NAMES), len(edits), len(binds), len(handovers)))
    if bad:
        print('REFUSED:')
        for b in bad[:30]:
            print('  ' + b)
        return 1
    if '--dry' in argv:
        return 0
    L = src.split('\n')
    # the bindings: `X = [v]` -> `em.name = v` (in place: a line may hold two)
    for name, s in binds.items():
        v = s.value.elts[0]
        edits.append((s.lineno, s.col_offset, s.end_col_offset,
                      'em.%s = %s' % (NAMES[name], ast.get_source_segment(src, v))))
    # hand-overs: whole lines, dropped
    drop = sorted((s.lineno for s in handovers.values()), reverse=True)
    for row, c0, c1, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        l = L[row - 1]
        L[row - 1] = l[:c0] + text + l[c1:]
    for row in drop:
        assert L[row - 1].strip().startswith('em.')
        del L[row - 1]
    # em made at the top of _prepare, and not again
    out = '\n'.join(L)
    L = out.split('\n')
    mk = [i for i, l in enumerate(L) if l == '    em = _Emitter()']
    assert len(mk) == 1
    del L[mk[0]]
    p = next(i for i, l in enumerate(L) if l.startswith('def _prepare('))
    t2 = ast.parse('\n'.join(L))
    prep2 = next(n for n in t2.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare')
    first = prep2.body[1] if isinstance(prep2.body[0], ast.Expr) else prep2.body[0]
    L[first.lineno - 1:first.lineno - 1] = [
        '    # THE EMITTER (_Emitter): made first, so the note\'s settings can be bound',
        '    # on it where they are introduced (em.channel, em.bend_row...)',
        '    em = _Emitter()']
    out = '\n'.join(L)
    ast.parse(out)
    open(SRC, 'w').write(out)
    print('written')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
