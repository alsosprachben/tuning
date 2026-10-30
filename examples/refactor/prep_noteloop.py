"""_prepare's note loop as a function: `for <note> in notes: <body>` becomes
`def _build_note(ev): <body>` and `for ev in notes: _build_note(ev)`.

    python3 examples/refactor/prep_noteloop.py [--dry]

The body's text stays where it is, at its indent; only the note loop's own
`continue`s become `return`. What could change meaning is checked first:

  - a name the body reads before binding it on some path may carry from
    one note to the next (the stops loop's `gain`, read by the release
    click) -- those are declared nonlocal, and bound-then-deleted in
    _prepare first, so the first note still finds them unbound as before
  - a closure outside the loop that reads a loop-bound name by late
    binding (_refl_norm read `props`) must read the emitter's (em.props,
    the same object) -- rewritten here
  - code after the loop that reads a loop-bound name: refused
  - a loop-level break or else: refused

Run examples/prepident.py after: the tables must not move.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'blockrender.py')


def main(argv):
    import prep_flow as F
    import exposed as X
    src = open(SRC).read()
    L = src.split('\n')
    st = F.stmts
    li = max((i for i, s in enumerate(st) if isinstance(s, ast.For)),
             key=lambda i: st[i].end_lineno - st[i].lineno)
    loop = st[li]
    bad = []
    if loop.orelse:
        bad.append('the note loop has an else')

    def own(node):
        stack = [node]
        while stack:
            n = stack.pop()
            yield n
            for c in ast.iter_child_nodes(n):
                if not isinstance(c, (ast.FunctionDef, ast.Lambda, ast.ClassDef, ast.For, ast.While)):
                    stack.append(c)
    conts, brks = [], []
    for b in loop.body:
        if isinstance(b, (ast.For, ast.While)):
            continue
        for n in own(b):
            if isinstance(n, ast.Continue):
                conts.append(n)
            elif isinstance(n, ast.Break):
                brks.append(n)
    if brks:
        bad.append('loop-level break at %s' % [n.lineno for n in brks])
    target = X._store_names(loop.target)
    body_binds = set(target)
    for b in loop.body:
        for x in ast.walk(b):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                body_binds.add(x.id)
            if isinstance(x, ast.FunctionDef):
                body_binds.add(x.name)
    glob = {g for x in ast.walk(F.prep) if isinstance(x, ast.Global) for g in x.names}
    if body_binds & glob:
        bad.append('the body binds a global: %s' % sorted(body_binds & glob))
    ex, _ = X.exposed(loop.body, set(target))
    carried = sorted(ex & body_binds)
    after, _ = X.exposed(st[li + 1:], set())
    if after & body_binds:
        bad.append('read after the loop: %s' % sorted(after & body_binds))
    late = []                       # (closure, names) outside the loop
    for i, s in enumerate(st):
        if i == li:
            continue
        for n in ast.walk(s):
            if isinstance(n, ast.FunctionDef):
                h = X._func_free(n) & body_binds
                if h:
                    late.append((n, h))
    for n, h in late:
        if h != {'props'}:
            bad.append('closure %s at %d reads loop-bound %s' % (n.name, n.lineno, sorted(h)))
    print('note loop at %d-%d: %d loop-level continue(s); carried %s; closures reading props: %s'
          % (loop.lineno, loop.end_lineno, len(conts), carried, [n.name for n, _ in late]))
    if bad:
        print('REFUSED:')
        for b in bad:
            print('  ' + b)
        return 1
    if '--dry' in argv:
        return 0

    edits = []                          # (row, c0, c1, text): single-line spans
    for c in conts:
        edits.append((c.lineno, c.col_offset, c.end_col_offset, 'return'))
    for n, h in late:
        for x in ast.walk(n):
            if isinstance(x, ast.Name) and x.id == 'props' and isinstance(x.ctx, ast.Load):
                edits.append((x.lineno, x.col_offset, x.end_col_offset, 'em.props'))
    for row, c0, c1, text in sorted(edits, reverse=True):
        l = L[row - 1]
        L[row - 1] = l[:c0] + text + l[c1:]
    # the header: `for <target> in notes:` -> the function and its call
    hdr = loop.lineno - 1
    body0 = loop.body[0].lineno - 1
    # (the header may run over lines, and comments may sit between it and
    # the body's first statement: those stay as the function's first lines)
    first = hdr
    while L[first].rstrip().endswith(('(', ',')) and first < body0:
        first += 1
    assert L[hdr].lstrip().startswith('for ') and L[first].rstrip().endswith(':')
    ind = L[hdr][:len(L[hdr]) - len(L[hdr].lstrip())]
    tgt = ast.unparse(loop.target)
    it = ast.unparse(loop.iter)
    head = []
    if carried:
        head += [ind + '# read before bound on some path, so carried note to note as the loop\'s',
                 ind + '# locals were (the stops loop\'s gain, read by the release click): bound',
                 ind + '# and deleted here, so the first note finds them unbound as it did',
                 ind + '%s = None' % ' = '.join(carried),
                 ind + 'del %s' % ', '.join(carried)]
    head += [ind + 'def _build_note(_ev):',
             ind + '    """One note of the note loop: its rows, and what it leaves for later passes."""']
    if carried:
        head.append(ind + '    nonlocal %s' % ', '.join(carried))
    head.append(ind + '    %s = _ev' % tgt)
    tail = ['', ind + 'for _ev in %s:' % it, ind + '    _build_note(_ev)']
    end = loop.end_lineno
    L[end:end] = tail
    L[hdr:first + 1] = head
    out = '\n'.join(L)
    ast.parse(out)
    open(SRC, 'w').write(out)
    print('written: _build_note; %d continue -> return; props via em in %s'
          % (len(conts), [n.name for n, _ in late]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
