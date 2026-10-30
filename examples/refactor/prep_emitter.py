"""Make _prepare's emitter an object: emit_partial, _reverse_rows and
_reverse_partial become methods of a module-level _Emitter, and the 43
names they read from _prepare become its attributes.

    python3 examples/refactor/prep_emitter.py [--dry]

THE STEP IS AN ALIAS, NOT A MOVE. Each name keeps its binding in _prepare;
right after it, the same object is handed to the emitter (`em.X = X`), and
the methods read self.X. A cell (`_TB = [...]`) is one list shared by both,
so the note loop's `_TB[0] = ...` reaches the method unchanged. What a
closure read by LATE binding -- props, rebound per note; four cells and
two helpers bound after the closures were made -- is handed over at each
place _prepare binds it, so the method sees what the closure saw. The
first call into the emitter comes after every one of those bindings
(checked here), and none of the names is rebound in between (also).

Run examples/prepident.py after: the tables must not move.
"""
import ast
import io
import os
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'blockrender.py')
METHODS = ('_reverse_partial', '_reverse_rows', 'emit_partial')


def selfify(text, names, own):
    """Each free NAME token in `names` -> self.NAME, except after '.', as a
    keyword argument's name, or the def's own name."""
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    out = []
    stack = []
    sig = [t for t in toks if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT,
                                              tokenize.INDENT, tokenize.DEDENT)]
    pos = {id(t): i for i, t in enumerate(sig)}
    edits = []
    for t in toks:
        if t.type == tokenize.OP and t.string in '([{':
            stack.append(t.string)
        elif t.type == tokenize.OP and t.string in ')]}':
            stack.pop()
        if t.type != tokenize.NAME or t.string not in names:
            continue
        i = pos[id(t)]
        prev = sig[i - 1] if i else None
        nxt = sig[i + 1] if i + 1 < len(sig) else None
        if prev is not None and prev.string == '.':
            continue
        if prev is not None and prev.string == 'def':
            continue
        if (nxt is not None and nxt.string == '=' and stack and stack[-1] == '('
                and prev is not None and prev.string in ('(', ',')):
            continue                    # f(name=...): a keyword, not the name
        edits.append(t.start)
    lines = text.split('\n')
    for (r, c) in sorted(edits, reverse=True):
        l = lines[r - 1]
        lines[r - 1] = l[:c] + 'self.' + l[c:]
    return '\n'.join(lines)


def main(argv):
    import prep_flow as F
    import exposed as X
    src = open(SRC).read()
    L = src.split('\n')
    st = F.stmts
    idx = {s.name: i for i, s in enumerate(st) if isinstance(s, ast.FunctionDef)}
    loc = set(F.localnames)
    C = set()
    for n in METHODS:
        C |= X._func_free(st[idx[n]]) & loc
    first = min(idx[n] for n in METHODS)
    bound_before = set(F.params)
    for j in range(first):
        bound_before |= F.DU[j][0]
    later = sorted(C - bound_before - set(METHODS))
    # the checks
    calls = {'emit_partial', '_reverse_rows', '_reverse_partial'}
    first_call = next(i for i, s in enumerate(st) if not isinstance(s, ast.FunctionDef)
                      and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                              and c.func.id in calls for c in ast.walk(s)))
    late_sites = {}             # name -> statement indices binding it (at _prepare's level)
    for n in later:
        late_sites[n] = [j for j in range(len(st)) if n in F.DU[j][0]]
    bad = []
    for n, js in late_sites.items():
        if n == 'props':
            continue
        if len(js) != 1 or js[0] >= first_call:
            bad.append('%s bound at %s, first call into the emitter at %d' % (n, js, first_call))
    for n in sorted(bound_before & C):
        reb = [j for j in range(first + 1, len(st)) if n in F.DU[j][0]]
        if reb:
            bad.append('%s is rebound after the emitter is made (statements %s)' % (n, reb))
    print('emitter: %d names; %d bound before it, %d after: %s'
          % (len(C), len(bound_before & C), len(later), ' '.join(later)))
    if bad:
        print('REFUSED:')
        for b in bad:
            print('  ' + b)
        return 1
    if '--dry' in argv:
        return 0

    # props: every binding at _prepare's own level, in or out of the loop
    prep = F.prep
    props_after = []

    def own(node):
        stack = [node]
        while stack:
            n = stack.pop()
            yield n
            for c in ast.iter_child_nodes(n):
                if not isinstance(c, (ast.FunctionDef, ast.Lambda, ast.ClassDef, ast.ListComp,
                                      ast.GeneratorExp, ast.SetComp, ast.DictComp)):
                    stack.append(c)
    for s in prep.body:
        for n in own(s):
            if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                tg = n.targets if isinstance(n, ast.Assign) else [n.target]
                if any(isinstance(x, ast.Name) and x.id == 'props' and isinstance(x.ctx, ast.Store)
                       for t in tg for x in ast.walk(t)):
                    props_after.append((n.end_lineno, n.col_offset))
            elif isinstance(n, (ast.For, ast.With)) or isinstance(n, ast.NamedExpr):
                tgt = getattr(n, 'target', None)
                if tgt is not None and any(isinstance(x, ast.Name) and x.id == 'props' and isinstance(x.ctx, ast.Store)
                                           for x in ast.walk(tgt)):
                    print('REFUSED: props bound by a for/with target at line %d' % n.lineno)
                    return 1

    # the methods' text, with the comment block above each
    def span(node):
        top = node.lineno - 1
        while top - 1 >= 0 and L[top - 1].strip().startswith('#'):
            top -= 1
        return top, node.end_lineno        # [top, end) in 0-based lines
    meth_text = []
    for n in METHODS:
        a, b = span(st[idx[n]])
        body = '\n'.join(L[a:b])
        body = body.replace('    def %s(' % n, '    def %s(self, ' % n, 1)
        meth_text.append(selfify(body, C, n))
    cls = ['class _Emitter(object):',
           '    """_prepare\'s emitter: emit_partial and the rows it writes. Its attributes',
           '    are the names the emitter reads -- the table (A), the current note\'s',
           '    settings, which the note loop writes into one-item cells (_TB, _MCH...),',
           '    and the voice (props) -- each the same object _prepare binds, handed',
           '    over where _prepare binds it (examples/refactor/prep_emitter.py)."""',
           '']
    cls.append('\n\n'.join(meth_text))
    cls += ['', '']

    # edits to _prepare, bottom-up
    edits = []                          # (line index to insert BEFORE, lines) or replacement
    for ln, col in props_after:
        edits.append(('ins', ln, [' ' * col + 'em.props = props']))
    for n in later:
        if n == 'props':
            continue
        j = late_sites[n][0]
        s = st[j]
        edits.append(('ins', s.end_lineno, ['    em.%s = %s' % (n, n)]))
    # the defs out, the emitter in at the first one's place
    spans = sorted(span(st[idx[n]]) for n in METHODS)
    head = ['    # THE EMITTER (_Emitter, above): the names it reads, handed to it as the',
            '    # same objects; what is bound later is handed over where it is bound.',
            '    em = _Emitter()']
    for n in sorted(bound_before & C):
        head.append('    em.%s = %s' % (n, n))
    for n in METHODS:
        head.append('    %s = em.%s' % (n, n))
    for (a, b) in spans:
        edits.append(('del', a, b))
    edits.append(('ins', spans[0][0], head))

    def key(e):
        return e[1]
    for e in sorted(edits, key=key, reverse=True):
        if e[0] == 'ins':
            L[e[1]:e[1]] = e[2]
        else:
            del L[e[1]:e[2]]
    p = next(i for i, l in enumerate(L) if l.startswith('def _prepare('))
    L[p:p] = cls
    out = '\n'.join(L)
    ast.parse(out)
    open(SRC, 'w').write(out)
    print('written: _Emitter with %s; %d handed over at the start, %d later, props at %d place(s)'
          % (', '.join(METHODS), len(bound_before & C), len(later) - 1, len(props_after)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
