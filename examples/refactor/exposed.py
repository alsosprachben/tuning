"""Upward-exposed reads of a statement list: names it may read before it
binds them, in execution order. bound = names definitely bound so far."""
import ast


def _targets(t):
    return {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}


def _expr_reads(e):
    """Free reads of an expression; lambdas/comprehensions bind their own."""
    if e is None:
        return set()
    r = set()

    def go(n, loc):
        if isinstance(n, ast.Name):
            if not isinstance(n.ctx, ast.Store) and n.id not in loc:
                r.add(n.id)
            return
        if isinstance(n, ast.Lambda):
            a = n.args
            for d in a.defaults + [d for d in a.kw_defaults if d is not None]:
                go(d, loc)
            go(n.body, loc | {x.arg for x in a.args + a.kwonlyargs} | ({a.vararg.arg} if a.vararg else set()) | ({a.kwarg.arg} if a.kwarg else set()))
            return
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            l2 = set(loc)
            for g in n.generators:
                go(g.iter, l2)
                l2 = l2 | _targets(g.target)
                for i in g.ifs:
                    go(i, l2)
            for f in ('elt', 'key', 'value'):
                if hasattr(n, f):
                    go(getattr(n, f), l2)
            return
        if isinstance(n, ast.NamedExpr):
            go(n.value, loc)
            return
        for c in ast.iter_child_nodes(n):
            go(c, loc)
    go(e, set())
    return r


def _func_free(n):
    """Free reads of a nested def's body, as read at the def (a closure)."""
    loc = {a.arg for a in n.args.args + n.args.kwonlyargs + getattr(n.args, 'posonlyargs', [])}
    if n.args.vararg: loc.add(n.args.vararg.arg)
    if n.args.kwarg: loc.add(n.args.kwarg.arg)
    ex, b = exposed(n.body, set(loc), func=True)
    stores = set()
    for x in ast.walk(n):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
            stores.add(x.id)
        if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x is not n:
            stores.add(x.name)
        if isinstance(x, (ast.Import, ast.ImportFrom)):
            for a in x.names:
                stores.add((a.asname or a.name).split('.')[0])
    # a name stored anywhere in a function is local to it (Python's rule)
    return ex - stores - loc


def exposed(stmts, bound, func=False):
    """(exposed reads, definitely bound after)."""
    ex = set()
    bound = set(bound)
    for s in stmts:
        e, bound = _stmt(s, bound)
        ex |= e
    return ex, bound


def _stmt(s, bound):
    def rd(*es):
        r = set()
        for e in es:
            r |= _expr_reads(e)
        return r - bound
    if isinstance(s, ast.Assign):
        e = rd(s.value, *[t for t in s.targets if not isinstance(t, ast.Name)])
        # subscript/attr targets read their base
        b = set(bound)
        for t in s.targets:
            b |= _store_names(t)
        return e, b
    if isinstance(s, ast.AugAssign):
        e = rd(s.value, s.target if not isinstance(s.target, ast.Name) else None)
        if isinstance(s.target, ast.Name) and s.target.id not in bound:
            e.add(s.target.id)
        return e, bound | _store_names(s.target)
    if isinstance(s, ast.AnnAssign):
        return rd(s.value), (bound | _store_names(s.target)) if s.value is not None else bound
    if isinstance(s, (ast.Expr, ast.Return)):
        return rd(s.value), bound
    if isinstance(s, ast.Delete):
        return rd(*[t for t in s.targets if not isinstance(t, ast.Name)]) | ({t.id for t in s.targets if isinstance(t, ast.Name)} - bound), bound - {t.id for t in s.targets if isinstance(t, ast.Name)}
    if isinstance(s, (ast.Import, ast.ImportFrom)):
        return set(), bound | {(a.asname or a.name).split('.')[0] for a in s.names}
    if isinstance(s, ast.FunctionDef):
        e = rd(*s.decorator_list, *s.args.defaults, *[d for d in s.args.kw_defaults if d is not None])
        e |= _func_free(s) - bound
        return e, bound | {s.name}
    if isinstance(s, ast.ClassDef):
        return rd(*s.bases), bound | {s.name}
    if isinstance(s, ast.If):
        e = rd(s.test)
        e1, b1 = exposed(s.body, bound)
        e2, b2 = exposed(s.orelse, bound)
        return e | e1 | e2, b1 & b2
    if isinstance(s, (ast.For, ast.AsyncFor)):
        e = rd(s.iter)
        b_in = bound | _store_names(s.target)
        e1, b1 = exposed(s.body, b_in)
        e2, _ = exposed(s.orelse, bound)
        # a second pass: names bound late in the body are read early on the
        # next iteration only if not bound before -- already counted above
        return e | e1 | e2, bound      # the loop may run zero times
    if isinstance(s, ast.While):
        e = rd(s.test)
        e1, _ = exposed(s.body, bound)
        e2, _ = exposed(s.orelse, bound)
        return e | e1 | e2, bound
    if isinstance(s, ast.With):
        e = set()
        b = set(bound)
        for it in s.items:
            e |= _expr_reads(it.context_expr) - b
            if it.optional_vars is not None:
                b |= _store_names(it.optional_vars)
        e1, b1 = exposed(s.body, b)
        return e | e1, b1
    if isinstance(s, ast.Try):
        e1, b1 = exposed(s.body, bound)
        e = set(e1)
        bs = [b1]
        for h in s.handlers:
            hb = bound | ({h.name} if h.name else set())
            eh, bh = exposed(h.body, hb)
            e |= eh | rd(h.type)
            bs.append(bh)
        eo, bo = exposed(s.orelse, b1)
        e |= eo
        bs[0] = bo
        after = set.intersection(*bs)
        ef, bf = exposed(s.finalbody, after)
        return e | ef, bf
    if isinstance(s, (ast.Pass, ast.Break, ast.Continue, ast.Global, ast.Nonlocal)):
        return set(), bound
    if isinstance(s, ast.Assert):
        return rd(s.test, s.msg), bound
    if isinstance(s, ast.Raise):
        return rd(s.exc, s.cause), bound
    # fallback: every read is exposed
    return _expr_reads(s) - bound, bound


def _store_names(t):
    return {x.id for x in ast.walk(t) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
