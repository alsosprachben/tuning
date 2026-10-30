"""Lift a run of _prepare's top-level statements into a module-level pass.

    python3 examples/refactor/prep_extract.py FIRST_LINE LAST_LINE NAME [--dry] [--head=REGEX]
    python3 examples/refactor/prep_extract.py --idx A B NAME [--dry] [--head=REGEX]

The tools that split blockrender._prepare (5533 lines, one function) into
named passes toward a native port. The code of a run moves unchanged into
`def NAME(inputs): ... return outputs` above _prepare, and the run becomes
one call. --idx takes statement indices (prep_flow.py curve lists them);
work bottom-up, so earlier indices stay put. --head starts the moved text
at the last comment line matching REGEX (a comment block that runs on
from another paragraph). The docstring it writes is a placeholder: write
the real one. Then:

    audit_closures.py                     no closure frozen to an input
    examples/prepident.py OUT 20 --against=REF   every table identical
    prep_inline.py NAME                   (to put a pass back and recut it)

exposed.py is the dataflow under it: the names a run may read before
binding them on every path (its inputs), and those after it reads (its
outputs).

FIRST_LINE/LAST_LINE: file lines of the first and last top-level statement
of the run (the comment block just above the first goes with it). Refuses
when the move could change behaviour:
  - a return/yield/global at the run's own level
  - a closure made in the run over a name _prepare rebinds after it
  - a closure made BEFORE the run over a name the run rebinds
  - an input not bound on every path before the run, or an output not
    bound on every path through it (unless the output is also bound before)
"""
import ast, builtins, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'blockrender.py')


def closures(stmt):
    """(node, free names, escapes-by-name) for each OUTERMOST function or lambda
    in stmt (an inner function is part of its outer one). A lambda that is a
    call's argument (a sort key) runs on the spot; any other lambda is
    stored, and may run later."""
    out = []
    parent = {}
    for n in ast.walk(stmt):
        for c in ast.iter_child_nodes(n):
            parent[c] = n

    def free(n):
        loc, reads = set(), set()
        args = n.args
        loc |= {a.arg for a in args.args + args.kwonlyargs + getattr(args, 'posonlyargs', [])}
        if args.vararg: loc.add(args.vararg.arg)
        if args.kwarg: loc.add(args.kwarg.arg)
        body = n.body if isinstance(n.body, list) else [n.body]
        for b in body:
            for x in ast.walk(b):
                if isinstance(x, ast.Name):
                    (loc.add(x.id) if isinstance(x.ctx, ast.Store) else reads.add(x.id))
                elif isinstance(x, ast.FunctionDef):
                    loc.add(x.name)
                    loc |= {a.arg for a in x.args.args}
                elif isinstance(x, ast.Lambda):
                    loc |= {a.arg for a in x.args.args}
                elif isinstance(x, ast.comprehension):
                    for y in ast.walk(x.target):
                        if isinstance(y, ast.Name): loc.add(y.id)
        return reads - loc

    stack = [stmt]
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.Lambda)):
            if isinstance(n, ast.Lambda):
                p = parent.get(n)
                stored = not (isinstance(p, ast.keyword) or (isinstance(p, ast.Call) and n in p.args))
                out.append((n, free(n), None if not stored else '<stored lambda>'))
            else:
                out.append((n, free(n), n.name))
            continue
        stack.extend(ast.iter_child_nodes(n))
    return out


def definite(stmts):
    """Names bound on every path through these statements (top level only)."""
    d = set()
    for s in stmts:
        if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in (s.targets if isinstance(s, ast.Assign) else [s.target]):
                for x in ast.walk(t):
                    if isinstance(x, ast.Name): d.add(x.id)
        elif isinstance(s, (ast.FunctionDef, ast.ClassDef)):
            d.add(s.name)
        elif isinstance(s, (ast.Import, ast.ImportFrom)):
            for a in s.names: d.add((a.asname or a.name).split('.')[0])
        elif isinstance(s, ast.If) and s.orelse:
            d |= definite(s.body) & definite(s.orelse)
        elif isinstance(s, ast.With):
            d |= definite(s.body)
            for it in s.items:
                if it.optional_vars is not None:
                    for x in ast.walk(it.optional_vars):
                        if isinstance(x, ast.Name): d.add(x.id)
        elif isinstance(s, ast.Try) and not s.handlers:
            d |= definite(s.body)
        elif isinstance(s, ast.Try):
            d |= definite(s.body) & set.intersection(*[definite(h.body) for h in s.handlers]) | definite(s.finalbody)
        elif isinstance(s, ast.Expr) and isinstance(s.value, ast.NamedExpr):
            d.add(s.value.target.id)
    return d


def main(argv):
    dry = '--dry' in argv
    head_re = next((x.split('=', 1)[1] for x in argv if x.startswith('--head=')), None)
    argv = [x for x in argv if x != '--dry' and not x.startswith('--head=')]
    src = open(SRC).read()
    lines = src.split('\n')
    import prep_flow as F
    stmts, DU, params, used_after = F.stmts, F.DU, F.params, F.used_after
    if argv[1] == '--idx':
        a, b, name = int(argv[2]), int(argv[3]), argv[4]
        first, last = stmts[a].lineno, stmts[b - 1].end_lineno
    else:
        first, last, name = int(argv[1]), int(argv[2]), argv[3]
        a = next(i for i, s in enumerate(stmts) if s.lineno == first)
        b = next(i for i, s in enumerate(stmts) if s.end_lineno == last) + 1
    import exposed as X
    seg = stmts[a:b]
    ex, seg_bound = X.exposed(seg, set())
    local = set(F.localnames)
    ins = ex & local
    seg_defs_all = set()
    for i in range(a, b): seg_defs_all |= DU[i][0]
    rest_ex, _ = X.exposed(stmts[b:], set())
    outs = seg_defs_all & rest_ex
    bad = []
    for s in seg:
        for x in ast.walk(s):
            if isinstance(x, (ast.Return, ast.Yield, ast.YieldFrom)):
                # only at the run's own level: inside a nested def is fine
                pass
    def own_level(node):
        stack = [node]
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            yield n
            stack.extend(ast.iter_child_nodes(n))
    for s in seg:
        for x in own_level(s):
            if isinstance(x, (ast.Return, ast.Yield, ast.YieldFrom, ast.Global, ast.Nonlocal)):
                bad.append('%s at line %d' % (type(x).__name__, x.lineno))
    seg_defs = set()
    for i in range(a, b): seg_defs |= DU[i][0]
    later_defs = set()
    for i in range(b, len(stmts)): later_defs |= DU[i][0]
    earlier_defs = set(params)
    for i in range(a): earlier_defs |= DU[i][0]
    def escapes(i, fname):
        """Can the closure made by statement i run after statement i? A def
        whose name a later statement reads; a stored lambda, always."""
        if fname is None:
            return False
        if fname == '<stored lambda>':
            return True
        return any(fname in DU[j][1] for j in range(i + 1, len(stmts)))
    for i in range(a, b):
        for fn, free, fname in closures(stmts[i]):
            # a name the run binds, OR one it takes as an input: either way the
            # pass's closure keeps the value the run saw, and _prepare's later
            # rebinding no longer reaches it
            hit = free & (seg_defs | ins) & later_defs
            if hit and escapes(i, fname):
                bad.append('closure at line %d reads %s, rebound after the run' % (fn.lineno, sorted(hit)))
    for i in range(a):
        for fn, free, fname in closures(stmts[i]):
            hit = free & seg_defs & earlier_defs
            if hit and escapes(i, fname):
                bad.append('closure at line %d (before the run) reads %s, rebound in the run' % (fn.lineno, sorted(hit)))
    before_def = X.exposed(stmts[:a], set(params))[1]
    soft_in = sorted(ins - before_def)
    if soft_in:
        bad.append('inputs not bound on every path before the run: %s' % soft_in)
    soft_out = sorted(outs - seg_bound - before_def)
    if soft_out:
        bad.append('outputs not bound on every path through the run: %s' % soft_out)
    # outputs bound only on some paths but bound before: pass them in too
    pass_through = sorted((outs - seg_bound) & before_def - ins)
    ins = sorted(ins | set(pass_through))
    outs = sorted(outs)
    print('run @%d-%d (%d statements, %d lines): in %d, out %d' % (first, last, b - a, last - first + 1, len(ins), len(outs)))
    print('  in : ' + ' '.join(ins))
    print('  out: ' + ' '.join(outs))
    if bad:
        print('REFUSED:')
        for x in bad: print('  ' + x)
        return 1
    if dry:
        return 0
    # the text: the comment block above the first statement goes with it
    top = first - 1
    while top - 1 >= 0 and lines[top - 1].strip().startswith('#'):
        top -= 1
    if head_re:
        hits = [i for i in range(top, first - 1) if re.search(head_re, lines[i])]
        if not hits:
            print('REFUSED: --head matched nothing in the comment block'); return 1
        top = hits[-1]
    body = lines[top:last]
    for l in body:
        if l.strip() and not l.startswith('    '):
            print('REFUSED: a line not indented under _prepare'); return 1
    ded = [l[4:] if l.startswith('    ') else l for l in body]
    head = ['def %s(%s):' % (name, ', '.join(ins))]
    doc = next((l.strip('# -').strip() for l in body if l.strip().startswith('#') and l.strip('# -').strip()), name)
    head.append('    """_prepare\'s pass: %s"""' % doc.replace('"', "'")[:300])
    ret = []
    if len(outs) == 1:
        ret = ['    return %s' % outs[0]]
    elif outs:
        ret = ['    return (%s)' % ', '.join(outs)]
    fn = head + ['    ' + l if l.strip() else '' for l in ded] + ret + ['', '']
    call_args = ', '.join(ins)
    if len(outs) == 1:
        call = '    %s = %s(%s)' % (outs[0], name, call_args)
    elif outs:
        call = '    (%s) = %s(%s)' % (', '.join(outs), name, call_args)
    else:
        call = '    %s(%s)' % (name, call_args)
    # wrap long lines at commas
    def wrap(s, ind):
        out, cur = [], ''
        for tok in re.split(r'(?<=, )', s):
            if len(cur) + len(tok) > 110 and cur:
                out.append(cur.rstrip()); cur = ind + tok
            else:
                cur += tok
        out.append(cur)
        return out
    callw = wrap(call, ' ' * 8)
    fn[0:1] = wrap(fn[0], ' ' * 8)
    if fn[-3].startswith('    return'):
        fn[-3:-2] = wrap(fn[-3], ' ' * 12)
    prep_line = next(i for i, l in enumerate(lines) if l.startswith('def _prepare('))
    new = lines[:prep_line] + fn + lines[prep_line:top] + callw + lines[last:]
    ast.parse('\n'.join(new))          # before writing: a bad cut leaves the file alone
    open(SRC, 'w').write('\n'.join(new))
    print('  written: %s (%d lines) before _prepare' % (name, len(fn)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
