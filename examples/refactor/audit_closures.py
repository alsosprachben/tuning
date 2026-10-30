"""Audit the extracted _prep_* passes: a closure a pass returns (or a stored
lambda) that reads one of the pass's INPUTS keeps the value it was handed,
so if _prepare rebinds that name after the call, the closure no longer
sees it -- where in _prepare's own scope it did. Prints each such closure;
there should be none.

    python3 examples/refactor/audit_closures.py
"""
import ast, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exposed as X
t=ast.parse(open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'blockrender.py')).read())
prep=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='_prepare')
passes={n.name:n for n in t.body if isinstance(n,ast.FunctionDef) and n.name.startswith('_prep_')}
stmts=prep.body
def binds(s):
    out=set()
    for x in ast.walk(s):
        if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Store): out.add(x.id)
        if isinstance(x,ast.FunctionDef): out.add(x.name)
    return out
B=[binds(s) for s in stmts]
problems=[]
for i,s in enumerate(stmts):
    for c in ast.walk(s):
        if isinstance(c,ast.Call) and isinstance(c.func,ast.Name) and c.func.id in passes:
            fn=passes[c.func.id]; params={a.arg for a in fn.args.args}
            rets=set()
            for r in ast.walk(fn):
                if isinstance(r,ast.Return) and r.value is not None:
                    rets|={x.id for x in ast.walk(r.value) if isinstance(x,ast.Name)}
            later=set().union(*B[i+1:]) if i+1<len(B) else set()
            for d in ast.walk(fn):
                if d is fn: continue
                if isinstance(d,ast.FunctionDef):
                    free=X._func_free(d); esc=d.name in rets
                elif isinstance(d,ast.Lambda):
                    free={x.id for x in ast.walk(d.body) if isinstance(x,ast.Name)}-{a.arg for a in d.args.args}; esc=True
                else: continue
                hit=free & params & later
                if hit and esc: problems.append((c.func.id, getattr(d,'name','lambda@%d'%d.lineno), sorted(hit)))
for p in problems: print(p)
print(len(problems),'closures frozen to an input _prepare rebinds later')
