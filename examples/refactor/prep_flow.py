"""_prepare's dataflow, by top-level statement: the names each binds (DU[i][0])
and reads (DU[i][1]), and seg_io(a, b) -- what a run of statements takes
from before it and hands to after it. Computed on import from the working
tree's blockrender.py.

    python3 prep_flow.py curve     live names across each statement
    python3 prep_flow.py segs      the commented blocks' inputs and outputs
"""
import ast, builtins, sys, os, collections, re
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'blockrender.py')
tree = ast.parse(open(SRC).read())
prep = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare')
modnames = set()
for n in tree.body:
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)): modnames.add(n.name)
    elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
            for x in ast.walk(t):
                if isinstance(x, ast.Name): modnames.add(x.id)
    elif isinstance(n, (ast.Import, ast.ImportFrom)):
        for a in n.names: modnames.add((a.asname or a.name).split('.')[0])
    elif isinstance(n, (ast.If, ast.Try)):
        for x in ast.walk(n):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store): modnames.add(x.id)
            if isinstance(x, (ast.Import, ast.ImportFrom)):
                for a in x.names: modnames.add((a.asname or a.name).split('.')[0])
            if isinstance(x, (ast.FunctionDef, ast.ClassDef)): modnames.add(x.name)
B = set(dir(builtins))
params = {a.arg for a in prep.args.args}

def defs_uses(stmt):
    """names this top-level statement binds in _prepare's scope, and names it reads from it"""
    d, u = set(), set()
    class V(ast.NodeVisitor):
        def __init__(s): s.scopes=[set()]
        def visit_FunctionDef(s, n):
            if s is top: pass
            d.add(n.name) if len(s.scopes)==1 else s.scopes[-1].add(n.name)
            for dec in n.decorator_list: s.visit(dec)
            for df in n.args.defaults + n.args.kw_defaults:
                if df is not None: s.visit(df)
            loc = {a.arg for a in n.args.args + n.args.kwonlyargs} | ({n.args.vararg.arg} if n.args.vararg else set()) | ({n.args.kwarg.arg} if n.args.kwarg else set())
            for x in ast.walk(n):
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store): loc.add(x.id)
                if isinstance(x, (ast.FunctionDef, ast.Lambda)) and x is not n:
                    pass
            nl = set()
            for x in ast.walk(n):
                if isinstance(x, ast.Nonlocal): nl |= set(x.names)
            loc -= nl
            d.update(nl & set())  # nonlocal writes: treat as use+def
            for x in nl: d.add(x); u.add(x)
            s.scopes.append(loc)
            for b in n.body: s.visit(b)
            s.scopes.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Lambda(s, n):
            loc = {a.arg for a in n.args.args}
            for df in n.args.defaults: s.visit(df)
            s.scopes.append(loc); s.visit(n.body); s.scopes.pop()
        def visit_comp(s, n):
            loc=set()
            for g in n.generators:
                for x in ast.walk(g.target):
                    if isinstance(x, ast.Name): loc.add(x.id)
            s.scopes.append(loc)
            for g in n.generators:
                s.visit(g.iter); [s.visit(i) for i in g.ifs]
            for f in ('elt','key','value'):
                if hasattr(n,f): s.visit(getattr(n,f))
            s.scopes.pop()
        visit_ListComp=visit_SetComp=visit_GeneratorExp=visit_DictComp=visit_comp
        def visit_Name(s, n):
            if any(n.id in sc for sc in s.scopes[1:]): return
            if isinstance(n.ctx, ast.Store): d.add(n.id)
            elif isinstance(n.ctx, ast.Del): d.add(n.id)
            else: u.add(n.id)
        def visit_Import(s, n):
            for a in n.names:
                nm=(a.asname or a.name).split('.')[0]
                (d.add(nm) if len(s.scopes)==1 else s.scopes[-1].add(nm))
        visit_ImportFrom = visit_Import
    top = V(); top.visit(stmt) if not isinstance(stmt, ast.FunctionDef) else top.visit_FunctionDef(stmt)
    return d, u

stmts = prep.body
DU = [defs_uses(s) for s in stmts]
localnames = set(params)
for d,u in DU: localnames |= d
DU = [(d & localnames, u & localnames) for d,u in DU]
N = len(stmts)
# live across cut before i: names defined in [0,i) (or params) used in [i,N)
used_after = [set() for _ in range(N+1)]
for i in range(N-1,-1,-1): used_after[i] = used_after[i+1] | DU[i][1]
defined_before = set(params); rows=[]
for i in range(N+1):
    live = defined_before & used_after[i] if i<N else set()
    rows.append(len(live))
    if i<N: defined_before |= DU[i][0]
if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv)>1 else 'curve'
    if mode == 'curve':
        print(N, 'top-level statements;', len(localnames), 'local names')
        db=set(params)
        for i,s in enumerate(stmts):
            live = db & used_after[i]
            kind = type(s).__name__ + (' '+s.name if isinstance(s, ast.FunctionDef) else '')
            if isinstance(s, ast.For): kind='For '+ast.unparse(s.target)[:30]
            print('%4d @%5d %5d lines  live-in %3d  defs %3d  %s' % (i, s.lineno, s.end_lineno-s.lineno+1, len(live), len(DU[i][0]), kind))
            db |= DU[i][0]
    elif mode == 'cut':
        a, b = int(sys.argv[2]), int(sys.argv[3])   # statement range [a,b)
        before=set(params)
        for i in range(a): before |= DU[i][0]
        ins=set(); outs=set(); defs=set()
        for i in range(a,b):
            ins |= (DU[i][1] - defs) & before
            defs |= DU[i][0]
        outs = defs & used_after[b]
        print('lines @%d-%d' % (stmts[a].lineno, stmts[b-1].end_lineno))
        print('IN  %d: %s' % (len(ins), ' '.join(sorted(ins))))
        print('OUT %d: %s' % (len(outs), ' '.join(sorted(outs))))

def seg_io(a, b):
    before=set(params)
    for i in range(a): before |= DU[i][0]
    ins=set(); defs=set()
    for i in range(a,b):
        ins |= (DU[i][1] - defs) & before
        defs |= DU[i][0]
    return ins, defs & used_after[b]

def comment_blocks():
    """group top-level statements into segments at blank-line + caps comment boundaries"""
    lines = open(SRC).read().splitlines()
    starts=[0]
    for i in range(1, 313):
        ln = stmts[i].lineno - 1
        j = ln - 1
        while j > 0 and lines[j].strip().startswith('#'): j -= 1
        head = [l.strip('# ').strip() for l in lines[j+1:ln]]
        if head and lines[j].strip()=='' and re.match(r"^[-\s]*[A-Z][A-Z0-9'`/ ,\-:()]{6,}", head[0] or ''):
            starts.append(i)
    return starts, lines
if __name__ == '__main__' and len(sys.argv)>1 and sys.argv[1]=='segs':
    import re
    starts, lines = comment_blocks()
    starts.append(313)
    for a,b in zip(starts, starts[1:]):
        ins, outs = seg_io(a,b)
        ln=stmts[a].lineno-1; j=ln-1
        while j>0 and lines[j].strip().startswith('#'): j-=1
        title=(lines[j+1].strip('# ').strip() if j+1<ln else '')[:60]
        n=stmts[b-1].end_lineno-stmts[a].lineno+1
        print('%3d-%3d @%5d %5d lines in %3d out %3d  %s' % (a,b,stmts[a].lineno,n,len(ins),len(outs),title))
