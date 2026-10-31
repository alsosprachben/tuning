"""Lift a run of _build_note's top-level statements -- a branch of the note
loop -- into a module-level function `NAME(em, props, nt, inputs...)`.

    python3 examples/refactor/note_extract.py --list
    python3 examples/refactor/note_extract.py --idx A B NAME [--dry]

prep_extract.py's step, one scope down. _build_note is nested in
_prepare, so a name it reads is its own local, a _prepare name (through
the closure) or a module global; the lifted function takes the first two
kinds as parameters -- those of em, props and nt it reads first (props is
not yet bound where the note's class is chosen), the rest sorted -- and
returns what it binds that the rest of the note reads. The code moves
unchanged. Refused, as there:

  - a return/yield/nonlocal/global at the run's own level (a `return` in
    the run is the note's own early exit: lifting it would not end the note)
  - an input not bound on every path before the run, or an output not
    bound on every path through it (unless bound before too)
  - a closure made in the run that outlives it (stored, or its name read
    after it) and reads a name rebound after the run
  - a write to one of _build_note's nonlocal names

--list prints _build_note's statements with their size, inputs and outputs.
Run examples/prepident.py after: the tables must not move.
"""
import ast
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'blockrender.py')
FIXED = ('em', 'props', 'nt')

import exposed as X  # noqa: E402


def load():
    src = open(SRC).read()
    t = ast.parse(src)
    prep = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare')
    bn = next(n for n in ast.walk(prep) if isinstance(n, ast.FunctionDef) and n.name == '_build_note')
    return src, t, prep, bn


def stores(node):
    out = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
            out.add(x.id)
        elif isinstance(x, (ast.FunctionDef, ast.ClassDef)):
            out.add(x.name)
        elif isinstance(x, (ast.Import, ast.ImportFrom)):
            out |= {(a.asname or a.name).split('.')[0] for a in x.names}
    return out


def own_level(node):
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def analyse(prep, bn, a, b):
    body = bn.body
    params = {x.arg for x in bn.args.args}
    nonloc = {g for s in body if isinstance(s, ast.Nonlocal) for g in s.names}
    bn_local = (stores(bn) | params) - nonloc
    # _prepare's OWN names: not those bound inside _build_note or any other
    # function nested in it
    prep_local = {x.arg for x in prep.args.args}
    for st in prep.body:
        for x in own_level(st):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                prep_local.add(x.id)
            elif isinstance(x, (ast.Import, ast.ImportFrom)):
                prep_local |= {(a.asname or a.name).split('.')[0] for a in x.names}
        if isinstance(st, (ast.FunctionDef, ast.ClassDef)):
            prep_local.add(st.name)
    for x in ast.walk(prep):
        if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x is not prep:
            prep_local.add(x.name)
    seg = body[a:b]
    ex, seg_bound = X.exposed(seg, set())
    ins = ex & (bn_local | prep_local)
    later_ex, _ = X.exposed(body[b:], set())
    seg_binds = set()
    for s in seg:
        seg_binds |= stores(s)
    outs = seg_binds & later_ex & bn_local
    bad = []
    for s in seg:
        for x in own_level(s):
            if isinstance(x, (ast.Return, ast.Yield, ast.YieldFrom, ast.Global, ast.Nonlocal)):
                bad.append('%s at line %d' % (type(x).__name__, x.lineno))
    if seg_binds & nonloc:
        bad.append('binds nonlocal %s' % sorted(seg_binds & nonloc))
    before = X.exposed(body[:a], params | (prep_local - nonloc))[1]
    soft_in = sorted((ins & bn_local) - before)
    if soft_in:
        bad.append('inputs not bound on every path before the run: %s' % soft_in)
    soft_out = sorted(outs - seg_bound - before)
    if soft_out:
        bad.append('outputs not bound on every path through the run: %s' % soft_out)
    pass_through = (outs - seg_bound) & before
    ins = ins | pass_through
    # closures made in the run must not escape it
    parent = {}
    for s in seg:
        for n in ast.walk(s):
            for c in ast.iter_child_nodes(n):
                parent[c] = n
    rest_reads = set()
    for s in body[b:]:
        rest_reads |= {x.id for x in ast.walk(s) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
    # a closure the run makes and keeps past it is a hazard only if it reads
    # a name rebound after the run -- in _build_note, or (being made per
    # note) any _prepare name bound more than once: moved, it would keep the
    # value it was handed
    later_binds = set()
    for s in body[b:]:
        later_binds |= stores(s)
    prep_count = {}
    for x in ast.walk(prep):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
            prep_count[x.id] = prep_count.get(x.id, 0) + 1
    rebound = later_binds | {k for k, v in prep_count.items() if v > 1}

    def lam_free(n):
        args = {a.arg for a in n.args.args + n.args.kwonlyargs}
        return {x.id for x in ast.walk(n.body) if isinstance(x, ast.Name)} - args
    for s in seg:
        stack = [s]
        while stack:
            n = stack.pop()
            if isinstance(n, ast.FunctionDef):
                hot = X._func_free(n) & rebound
                if n.name in rest_reads and hot:
                    bad.append('closure %s at %d outlives the run and reads %s, rebound after it'
                               % (n.name, n.lineno, sorted(hot)))
                continue
            if isinstance(n, ast.Lambda):
                p = parent.get(n)
                called_here = isinstance(p, ast.keyword) or (isinstance(p, ast.Call) and n in p.args)
                hot = lam_free(n) & rebound
                if not called_here and hot:
                    bad.append('lambda at %d is kept and reads %s, rebound after the run'
                               % (n.lineno, sorted(hot)))
                continue
            stack.extend(ast.iter_child_nodes(n))
    fixed = [x for x in FIXED if x in ex]      # em, props, nt: those the run reads
    ins -= set(FIXED)
    return fixed + sorted(ins), sorted(outs), bad


def main(argv):
    src, t, prep, bn = load()
    body = bn.body
    if '--list' in argv:
        for i, s in enumerate(body):
            n = s.end_lineno - s.lineno + 1
            if n < int(next((x.split('=')[1] for x in argv if x.startswith('--min=')), 1)):
                continue
            ins, outs, bad = analyse(prep, bn, i, i + 1)
            print('%3d @%5d %4d  in %2d out %2d %s  %s' % (i, s.lineno, n, len(ins), len(outs),
                                                         'REF' if bad else '   ',
                                                         ast.unparse(s).split('\n')[0][:70]))
        return 0
    dry = '--dry' in argv
    args = [x for x in argv if not x.startswith('--')]
    a, b, name = int(args[1]), int(args[2]), args[3]
    ins, outs, bad = analyse(prep, bn, a, b)
    first, last = body[a].lineno, body[b - 1].end_lineno
    print('run @%d-%d (%d statements, %d lines): in %d, out %d' % (first, last, b - a, last - first + 1,
                                                                    len(ins), len(outs)))
    print('  in : ' + ' '.join(ins))
    print('  out: ' + ' '.join(outs))
    if bad:
        print('REFUSED:')
        for x in bad:
            print('  ' + x)
        return 1
    if dry:
        return 0
    L = src.split('\n')
    top = first - 1
    while top - 1 >= 0 and L[top - 1].strip().startswith('#'):
        top -= 1
    text = L[top:last]
    ind = len(L[first - 1]) - len(L[first - 1].lstrip())
    for l in text:
        if l.strip() and len(l) - len(l.lstrip()) < ind:
            print('REFUSED: a line less indented than the run'); return 1
    ded = [l[ind:] if l.strip() else '' for l in text]
    doc = next((l.strip('# -').strip() for l in ded if l.startswith('#') and l.strip('# -').strip()), name)
    sig = 'def %s(%s):' % (name, ', '.join(ins))
    fn = textwrap.wrap(sig, 110, subsequent_indent=' ' * 8, break_long_words=False, break_on_hyphens=False)
    fn.append('    """_build_note\'s branch: %s"""' % doc.replace('"', "'")[:300])
    fn += ['    ' + l if l else '' for l in ded]
    if outs:
        r = 'return %s' % outs[0] if len(outs) == 1 else 'return (%s)' % ', '.join(outs)
        fn += textwrap.wrap(r, 106, initial_indent='    ', subsequent_indent=' ' * 12, break_long_words=False)
    fn += ['', '']
    call = '%s(%s)' % (name, ', '.join(ins))
    if len(outs) == 1:
        call = '%s = %s' % (outs[0], call)
    elif outs:
        call = '(%s) = %s' % (', '.join(outs), call)
    pad = ' ' * ind
    callw = textwrap.wrap(call, 110 - ind, initial_indent=pad, subsequent_indent=pad + ' ' * 8,
                          break_long_words=False, break_on_hyphens=False)
    at = next(i for i, l in enumerate(L) if l.startswith('def _prepare('))
    new = L[:at] + fn + L[at:top] + callw + L[last:]
    out = '\n'.join(new)
    ast.parse(out)
    open(SRC, 'w').write(out)
    print('  written: %s (%d lines)' % (name, len(fn)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
