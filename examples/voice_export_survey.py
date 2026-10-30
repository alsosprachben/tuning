#!/usr/bin/env python3
"""What a native port of the voices would have to carry: the class tree
resolved, the way an exporter would flatten it.

    python3 examples/voice_export_survey.py [--json OUT.json] [--bodies NAME]

Every voice is a SynthProperties subclass (744 in tonelib, more made at import
by patch_map and percussion_map: variations, ringing keys, reversed and
randomised strokes). A native runtime would not mirror that tree; it would
take one flat record per class -- each constant resolved through the MRO, and
for each method WHICH BODY the MRO picks. This survey counts what that costs:

  methods    each method name the tree defines; how many distinct bodies
             (the functions a port writes) and how many classes use each
  bodies     what each body reads: self constants, self methods, module
             globals (and of what kind), imports inside it, randomness,
             numpy, and writes to self outside __init__ (state)
  constants  each class attribute's type, so the blob's shape is known:
             numbers and numeric tuples export as data; classes, functions
             and objects stored as attributes need a decision each
  creation   __init__ (instance state) and __init_subclass__ (computed when
             the class is made -- the exporter records the results)

--json writes the per-class records (resolved owner per method, constants'
types) and the per-body read sets, for the exporter proper to start from.
--bodies NAME prints each distinct body of one method, its owners and reads.
"""
import ast
import builtins
import collections
import inspect
import json
import os
import sys
import textwrap
import types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import tonelib  # noqa: E402
import patch_map  # noqa: E402,F401  (makes the variation classes)
import percussion_map  # noqa: E402,F401  (and the kit's)

ROOT = tonelib.SynthProperties
FUNC_KINDS = (types.FunctionType, staticmethod, classmethod, property)


def all_voices():
    seen, todo = set(), [ROOT]
    while todo:
        c = todo.pop()
        for s in c.__subclasses__():
            if s not in seen:
                seen.add(s)
                todo.append(s)
    return [ROOT] + sorted(seen, key=lambda c: (c.__module__, c.__qualname__))


def tree_classes(voices):
    """Every class a voice's MRO passes through, but object's own."""
    out = set()
    for v in voices:
        out.update(k for k in v.__mro__ if k is not object)
    return out


def func_of(v):
    if isinstance(v, (staticmethod, classmethod)):
        return v.__func__
    if isinstance(v, property):
        return v.fget
    return v if isinstance(v, types.FunctionType) else None


def kind_of(val):
    """The constant's type as the blob would see it."""
    if val is None:
        return "none"
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, str):
        return "str"
    if isinstance(val, type):
        return "class"
    if callable(val):
        return "callable"
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            return "ndarray" if val.dtype.kind in "biuf" else "ndarray-obj"
        if isinstance(val, np.generic):
            return "number"
    except ImportError:
        pass
    if isinstance(val, (tuple, list, frozenset, set)):
        kinds = {kind_of(x) for x in val}
        kinds.discard("none")
        if not kinds or kinds <= {"number", "bool", "numeric-seq"}:
            return "numeric-seq"
        if kinds <= {"number", "bool", "numeric-seq", "str", "mixed-seq"}:
            return "mixed-seq"
        return "seq-of:" + ",".join(sorted(k for k in kinds if k not in ("number", "bool", "numeric-seq")))
    if isinstance(val, dict):
        kinds = {kind_of(x) for x in val.values()}
        kinds.discard("none")
        return "dict" if kinds <= {"number", "bool", "numeric-seq", "str", "mixed-seq"} else "dict-of:" + ",".join(sorted(kinds))
    return "object:" + type(val).__name__


def numbers_in(val, depth=0):
    if depth > 6:
        return 0
    if isinstance(val, bool) or val is None or isinstance(val, str):
        return 0
    if isinstance(val, (int, float)):
        return 1
    try:
        import numpy as np
        if isinstance(val, np.ndarray) and val.dtype.kind in "biuf":
            return int(val.size)
    except ImportError:
        pass
    if isinstance(val, (tuple, list)):
        return sum(numbers_in(x, depth + 1) for x in val)
    if isinstance(val, dict):
        return sum(numbers_in(x, depth + 1) for x in val.values())
    return 0


def body_reads(fn):
    """What one function body reads, from its source and its globals."""
    out = dict(lines=0, self_reads=set(), self_writes=set(), globals={}, imports=set(),
               random=False, numpy=False, source=None, error=None)
    try:
        src = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError, IndentationError) as e:
        out["error"] = type(e).__name__
        return out
    out["source"] = src
    out["lines"] = src.count("\n")
    args = fn.__code__.co_varnames[:1]
    me = args[0] if args else "self"
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in (me, "cls"):
            (out["self_writes"] if isinstance(n.ctx, ast.Store) else out["self_reads"]).add(n.attr)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            mod = n.module if isinstance(n, ast.ImportFrom) else None
            for a in n.names:
                out["imports"].add(mod or a.name)
    try:
        cv = inspect.getclosurevars(fn)
        refs = dict(cv.globals)
        refs.update(cv.nonlocals)
    except (TypeError, ValueError):
        refs = {}
    for name, val in refs.items():
        if isinstance(val, types.ModuleType):
            k = "module:" + val.__name__
            if val.__name__ in ("random", "numpy.random"):
                out["random"] = True
            if val.__name__.startswith("numpy"):
                out["numpy"] = True
        elif isinstance(val, type):
            k = "class"
        elif callable(val):
            mod = getattr(val, "__module__", "") or ""
            k = "function:" + mod
            if mod in ("random",) or "random" in name:
                out["random"] = True
            if mod.startswith("numpy"):
                out["numpy"] = True
        else:
            k = "const:" + kind_of(val)
        out["globals"][name] = k
    if out["imports"] & {"numpy", "numpy.random"}:
        out["numpy"] = True
    if "random" in out["imports"]:
        out["random"] = True
    return out


def main(argv):
    jpath = argv[argv.index("--json") + 1] if "--json" in argv else None
    show = argv[argv.index("--bodies") + 1] if "--bodies" in argv else None

    voices = all_voices()
    tree = tree_classes(voices)
    made = [v for v in voices if v.__module__ != "tonelib"]

    # every name any class in the tree defines, split methods / constants
    method_names, const_names = set(), set()
    for k in tree:
        for name, val in vars(k).items():
            if name.startswith("__") and name not in ("__init__", "__init_subclass__"):
                continue
            (method_names if isinstance(val, FUNC_KINDS) else const_names).add(name)

    # per voice: which class's body each method resolves to
    owner = {}                  # (voice, name) -> defining class
    for v in voices:
        for k in v.__mro__:
            for name, val in vars(k).items():
                if name in method_names and (v, name) not in owner and isinstance(val, FUNC_KINDS):
                    owner[(v, name)] = k

    users = collections.defaultdict(collections.Counter)      # name -> {owner: n voices}
    for (v, name), k in owner.items():
        users[name][k] += 1

    bodies = {}                 # (owner, name) -> reads
    for name, ks in users.items():
        for k in ks:
            bodies[(k, name)] = body_reads(func_of(vars(k)[name]))

    # ---- report
    print("VOICES  %d SynthProperties classes (%d in tonelib, %d made at import by %s)"
          % (len(voices), len(voices) - len(made), len(made),
             ", ".join("%s %d" % kv for kv in collections.Counter(c.__module__ for c in made).most_common())))
    mixins = [k for k in tree if not issubclass(k, ROOT)]
    print("        %d classes in their MROs, %d of them mixins outside the root" % (len(tree), len(mixins)))
    depth = max(len([k for k in v.__mro__ if k is not object]) for v in voices)
    multi = sum(len(v.__bases__) > 1 for v in voices)
    print("        deepest MRO %d classes; %d voices with more than one base" % (depth, multi))

    nb = len(bodies)
    lines = sum(b["lines"] for b in bodies.values())
    over = {n: ks for n, ks in users.items() if len(ks) > 1}
    print("\nMETHODS %d names; %d distinct bodies, %d lines; %d names have more than one body"
          % (len(users), nb, lines, len(over)))
    print("        %-34s %6s %6s %6s  %s" % ("name", "bodies", "lines", "voices", "most-used owner"))
    rows = sorted(users.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for name, ks in rows[:45]:
        ln = sum(bodies[(k, name)]["lines"] for k in ks)
        top, n = ks.most_common(1)[0]
        print("        %-34s %6d %6d %6d  %s (%d)" % (name, len(ks), ln, sum(ks.values()), top.__name__, n))
    single = [n for n, ks in users.items() if len(ks) == 1]
    print("        ... and %d names with one body (%d lines)"
          % (len(single), sum(bodies[(next(iter(users[n])), n)]["lines"] for n in single)))

    # what the bodies read
    gk = collections.Counter()
    for b in bodies.values():
        for g, k in b["globals"].items():
            gk[k.split(":")[0] if not k.startswith("module") else k] += 1
    rnd = sum(b["random"] for b in bodies.values())
    npy = sum(b["numpy"] for b in bodies.values())
    imp = collections.Counter(i for b in bodies.values() for i in b["imports"])
    st = [(k, n) for (k, n), b in bodies.items()
          if n not in ("__init__", "__init_subclass__") and b["self_writes"]]
    err = [(k, n) for (k, n), b in bodies.items() if b["error"]]
    print("\nBODIES  read module globals: " + ", ".join("%s %d" % kv for kv in gk.most_common(12)))
    print("        %d use randomness, %d numpy; imports inside bodies: %s"
          % (rnd, npy, ", ".join("%s %d" % kv for kv in imp.most_common(12)) or "none"))
    print("        %d bodies write to self outside __init__ (state a flat record must carry): %s"
          % (len(st), ", ".join(sorted({n for _, n in st}))[:300]))
    if err:
        print("        %d bodies without source: %s" % (len(err), ", ".join("%s.%s" % (k.__name__, n) for k, n in err[:8])))
    fns = collections.Counter(g for b in bodies.values() for g, k in b["globals"].items() if k.startswith("function"))
    print("        module functions most called: " + ", ".join("%s %d" % kv for kv in fns.most_common(15)))

    # constants
    ck = collections.Counter()
    odd = collections.defaultdict(list)
    nums = 0
    per_name_kinds = collections.defaultdict(set)
    for v in voices:
        for name in const_names:
            try:
                val = inspect.getattr_static(v, name)
            except AttributeError:
                continue
            kd = kind_of(val)
            per_name_kinds[name].add(kd)
            if kd not in ("none", "bool", "number", "str", "numeric-seq", "mixed-seq", "dict", "ndarray"):
                odd[kd].append("%s.%s" % (v.__name__, name))
            nums += numbers_in(val)
            ck[kd] += 1
    dist = collections.Counter()
    for name in const_names:
        vals = set()
        for v in voices:
            try:
                vals.add(repr(inspect.getattr_static(v, name)))
            except AttributeError:
                pass
        dist[name] = len(vals)
    print("\nCONSTANTS %d names; %d (voice, name) values: %s"
          % (len(const_names), sum(ck.values()), ", ".join("%s %d" % kv for kv in ck.most_common())))
    print("        %d numbers in all, resolved per voice (%.1f MB as float32, before sharing equal tables)"
          % (nums, nums * 4 / 1e6))
    print("        names whose value varies most across voices: "
          + ", ".join("%s %d" % kv for kv in dist.most_common(12)))
    print("        names that never vary (one value for every voice): %d" % sum(1 for n in dist if dist[n] == 1))
    for kd, xs in sorted(odd.items(), key=lambda kv: -len(kv[1])):
        names = collections.Counter(x.split(".", 1)[1] for x in xs)
        print("        NEEDS A DECISION %-22s %4d values, names: %s"
              % (kd, len(xs), ", ".join("%s %d" % kv for kv in names.most_common(6))))

    # creation-time work
    inits = [k for k in tree if "__init__" in vars(k)]
    subs = [k for k in tree if "__init_subclass__" in vars(k)]
    iw = collections.Counter(a for k in inits for a in bodies.get((k, "__init__"), {}).get("self_writes", ()))
    print("\nCREATION %d __init__ bodies; instance attributes they set (top): %s"
          % (len(inits), ", ".join("%s %d" % kv for kv in iw.most_common(14))))
    print("        %d __init_subclass__ (computed as each class is made; the exporter records the result): %s"
          % (len(subs), ", ".join(k.__name__ for k in subs)))
    sigs = collections.Counter(str(inspect.signature(vars(k)["__init__"])) for k in inits)
    print("        __init__ signatures: " + "; ".join("%s x%d" % kv for kv in sigs.most_common(6)))

    if show:
        print("\n== %s" % show)
        for k, n in users.get(show, {}).most_common():
            b = bodies[(k, show)]
            print("\n-- %s.%s  (%d voices, %d lines)" % (k.__qualname__, show, n, b["lines"]))
            print("   self: " + ", ".join(sorted(b["self_reads"])))
            print("   globals: " + ", ".join("%s=%s" % kv for kv in sorted(b["globals"].items())))

    if jpath:
        rec = {}
        for v in voices:
            r = {"module": v.__module__, "bases": [b.__name__ for b in v.__bases__],
                 "methods": {}, "constants": {}}
            for name in users:
                k = owner.get((v, name))
                if k is not None:
                    r["methods"][name] = "%s.%s" % (k.__module__, k.__qualname__)
            for name in const_names:
                try:
                    r["constants"][name] = kind_of(inspect.getattr_static(v, name))
                except AttributeError:
                    pass
            rec["%s.%s" % (v.__module__, v.__qualname__)] = r
        bj = {"%s.%s.%s" % (k.__module__, k.__qualname__, n):
              {"lines": b["lines"], "self_reads": sorted(b["self_reads"]),
               "self_writes": sorted(b["self_writes"]), "globals": b["globals"],
               "imports": sorted(b["imports"]), "random": b["random"], "numpy": b["numpy"]}
              for (k, n), b in bodies.items()}
        with open(jpath, "w") as f:
            json.dump({"voices": rec, "bodies": bj}, f, indent=1, sort_keys=True)
        print("\n  " + jpath)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
