"""The note as an object: _build_note's note-wide values -- the event, the
pitch, the times, the ears, the chiff -- become attributes of a _Note made
at its top (`f0` -> `nt.f0`, `_raw_off` -> `nt.key_off`), so a branch of
the note loop can be lifted out as `branch(em, props, nt)`.

    python3 examples/refactor/prep_note.py [--dry]

Every occurrence of one of NAMES in _build_note -- read, bound, in a
closure inside it -- is rewritten, scope-aware: a nested function, lambda
or comprehension that binds the same name keeps its own. Refused: a name
of NAMES declared nonlocal/global, bound by a walrus or `except ... as`
(none can be an attribute), or read in _build_note before it is bound.

Run examples/prepident.py after: the tables must not move.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'blockrender.py')

NAMES = {
    # the event
    'ch': 'ch', 'note': 'note', 'on': 'on', 'off': 'off', 'vel': 'vel',
    'v7': 'v7', 'v11': 'v11', 'pan': 'pan', 'prog': 'prog',
    '_raw_off': 'key_off',      # when the KEY came up, before any pedal held it
    # what plays it
    'drum': 'drum', 'organ': 'organ', 'pc': 'pc', '_orgk': 'organ_key',
    'FREQ_N': 'freq',           # the tuning table it is tuned in
    'chan_vol': 'chan_vol', '_EFG': 'efx_gain',
    # its pitch, times and envelope, in samples where emit_partial takes them
    'f0': 'f0', 'non': 'non', 'noff': 'noff', 'fade': 'fade', 'rel': 'rel',
    'chiff': 'chiff', 'cv': 'cv', 'cc': 'cc', 'crl': 'crl', 'csc': 'csc', 'sjit': 'sjit',
    # where it is heard
    'li': 'li', 'ri': 'ri',
    '_row0': 'row0',            # its first row in the table
}

SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ListComp, ast.SetComp,
          ast.GeneratorExp, ast.DictComp)


def bound_in(scope):
    """Names a nested scope binds itself (so ours are shadowed there)."""
    out = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = scope.args
        out |= {x.arg for x in a.args + a.kwonlyargs + getattr(a, 'posonlyargs', [])}
        if a.vararg:
            out.add(a.vararg.arg)
        if a.kwarg:
            out.add(a.kwarg.arg)
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        for b in body:
            for x in ast.walk(b):
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                    out.add(x.id)
    else:
        for g in scope.generators:
            out |= {x.id for x in ast.walk(g.target) if isinstance(x, ast.Name)}
    return out


def main(argv):
    src = open(SRC).read()
    t = ast.parse(src)
    prep = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare')
    bn = next(n for n in ast.walk(prep) if isinstance(n, ast.FunctionDef) and n.name == '_build_note')
    bad = []
    edits = []

    def visit(node, shadow):
        if isinstance(node, SCOPES) and node is not bn:
            inner = shadow | (bound_in(node) & set(NAMES))
            # a comprehension's first iterable is evaluated in the enclosing scope
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                visit(node.generators[0].iter, shadow)
                for g in node.generators:
                    for x in [g.target] + g.ifs + ([g.iter] if g is not node.generators[0] else []):
                        visit(x, inner)
                for f in ('elt', 'key', 'value'):
                    if hasattr(node, f):
                        visit(getattr(node, f), inner)
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list + node.args.defaults + [k for k in node.args.kw_defaults if k]:
                    visit(d, shadow)
                for b in node.body:
                    visit(b, inner)
                return
            if isinstance(node, ast.Lambda):
                for d in node.args.defaults:
                    visit(d, shadow)
                visit(node.body, inner)
                return
        if isinstance(node, (ast.Nonlocal, ast.Global)) and set(node.names) & set(NAMES) - shadow:
            bad.append('%s %s at %d' % (type(node).__name__, sorted(set(node.names) & set(NAMES)), node.lineno))
        if isinstance(node, ast.NamedExpr) and node.target.id in NAMES and node.target.id not in shadow:
            bad.append('walrus binds %s at %d' % (node.target.id, node.lineno))
        if isinstance(node, ast.ExceptHandler) and node.name in NAMES and node.name not in shadow:
            bad.append('except ... as %s at %d' % (node.name, node.lineno))
        if isinstance(node, ast.Name) and node.id in NAMES and node.id not in shadow:
            if node.lineno != node.end_lineno:
                bad.append('%s over lines at %d' % (node.id, node.lineno))
            edits.append((node.lineno, node.col_offset, node.end_col_offset, 'nt.' + NAMES[node.id]))
        for c in ast.iter_child_nodes(node):
            visit(c, shadow)

    for s in bn.body:
        visit(s, set())
    # read before bound: a carried value would be lost to a fresh _Note
    sys.path.insert(0, HERE)
    import exposed as X
    ex, _ = X.exposed(bn.body, {a.arg for a in bn.args.args})
    if ex & set(NAMES):
        bad.append('read before bound in _build_note: %s' % sorted(ex & set(NAMES)))
    # and nothing outside _build_note may read them as its locals (they were)
    used = {}
    for n in ast.walk(bn):
        if isinstance(n, ast.Name) and n.id in NAMES:
            used[n.id] = used.get(n.id, 0) + 1
    print('note: %d names, %d occurrences rewritten (%s)'
          % (len(NAMES), len(edits), ', '.join('%s %d' % kv for kv in sorted(used.items(), key=lambda kv: -kv[1])[:12])))
    unused = sorted(set(NAMES) - set(used))
    if unused:
        bad.append('not used in _build_note: %s' % unused)
    if bad:
        print('REFUSED:')
        for b in bad[:30]:
            print('  ' + b)
        return 1
    if '--dry' in argv:
        return 0
    L = src.split('\n')
    for row, c0, c1, text in sorted(edits, reverse=True):
        l = L[row - 1]
        L[row - 1] = l[:c0] + text + l[c1:]
    # nt made first in _build_note, after its docstring and nonlocal
    i = bn.body[0].lineno - 1
    k = 0
    while isinstance(bn.body[k], (ast.Expr, ast.Nonlocal)) and (not isinstance(bn.body[k], ast.Expr)
                                                                  or isinstance(bn.body[k].value, ast.Constant)):
        k += 1
    at = bn.body[k].lineno - 1
    ind = L[at][:len(L[at]) - len(L[at].lstrip())]
    L[at:at] = [ind + 'nt = _Note()']
    # the class, before _Emitter
    c = next(i for i, l in enumerate(L) if l.startswith('class _Emitter('))
    slots = ', '.join("'%s'" % v for v in NAMES.values())
    cls = ['class _Note(object):',
           '    """One note of the note loop, as _build_note works it out: the event',
           '    (ch, note, on, off, vel, v7, v11, pan, prog, key_off), what plays it',
           '    (drum, organ, pc, organ_key, freq, chan_vol, efx_gain), its pitch, times',
           '    and envelope in samples (f0, non, noff, fade, rel, chiff, cv, cc, crl,',
           '    csc, sjit), where it is heard (li, ri) and its first row (row0) --',
           '    what the note loop\'s branches read (examples/refactor/prep_note.py)."""',
           '']
    import textwrap
    cls += textwrap.wrap('__slots__ = (%s)' % slots, 100, initial_indent='    ', subsequent_indent='                 ')
    cls += ['', '']
    L[c:c] = cls
    out = '\n'.join(L)
    ast.parse(out)
    open(SRC, 'w').write(out)
    print('written: _Note, nt made at line %d' % (at + 1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
