#!/usr/bin/env python3
"""What a native port of the ENGINE would carry: the code that turns a voice
record and a note into rows of partials, and what live does to them after.

    python3 examples/engine_survey.py [--templates] [--json OUT.json]

examples/voice_export.py flattened the voices (1605 records, 230 method
bodies). The records are read by:

  blockrender._prepare   one function: parse, tune, every pass over the
                         notes, the note loop that emits rows (emit_partial),
                         and the packing for the kernel
  live                   no builder of its own: each (program, note,
                         velocity band) is built ONCE through blockrender's
                         prepare on an in-memory file -- a template -- then
                         stamped into a slab at note-on, and everything a
                         player does after (pedal, bend, slur, stops, the
                         register) is live's own code on the stamped rows
  tonelib.SynthTone /    the old per-sample renderer; blockrender does not
  BasePartial            call them, so they are not part of a port

This survey reports:

  prepare    _prepare's top-level structure (nested helpers, passes, the
             note loop) and the note loop's branches: each `if` with the
             voice features its test reads, its size and its emit_partial
             calls -- the engine's real dispatch points
  features   which voice fields and methods _prepare, live and the voice
             bodies read; fields read by none (dead, or read by string)
  live       live's classes and their size: what a native live keeps
             even with templates baked offline
  templates  (--templates) rows and bytes of a sample of templates, and a
             bank estimate: the size of shipping templates instead of the
             builder

Reads source and imports; builds nothing unless --templates.
"""
import ast
import collections
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

VOICE_VARS = {"props", "pc", "_spc", "_pcm", "_wsrc", "rp", "_tsrc", "spv", "cls", "_cls",
              "_pc", "vc", "_vc", "voice", "_voice", "klass", "_klass"}


def voice_names():
    """Field and method names of the voices, from the live classes."""
    import voice_export_survey as SV
    voices = SV.all_voices()
    fields, methods = set(), set()
    for k in SV.tree_classes(voices):
        for name, val in vars(k).items():
            if name.startswith("__"):
                continue
            (methods if isinstance(val, SV.FUNC_KINDS) and not isinstance(val, property)
             else fields).add(name)
    return fields, methods, voices, SV


class Reads(ast.NodeVisitor):
    """Voice attribute reads under a node: obj.name, getattr/hasattr(obj, 'name')."""
    def __init__(self, names, vars_=VOICE_VARS):
        self.names, self.vars = names, vars_
        self.found = collections.Counter()
        self.emits = 0
        self.calls = collections.Counter()

    def visit_Attribute(self, n):
        if isinstance(n.value, ast.Name) and n.value.id in self.vars and n.attr in self.names:
            self.found[n.attr] += 1
        self.generic_visit(n)

    def visit_Call(self, n):
        f = n.func
        if isinstance(f, ast.Name):
            if f.id in ("getattr", "hasattr") and len(n.args) >= 2 \
                    and isinstance(n.args[0], ast.Name) and n.args[0].id in self.vars \
                    and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str) \
                    and n.args[1].value in self.names:
                self.found[n.args[1].value] += 1
            if f.id == "emit_partial":
                self.emits += 1
            self.calls[f.id] += 1
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            self.calls["%s.%s" % (f.value.id, f.attr)] += 1
        self.generic_visit(n)


def reads(node, names):
    r = Reads(names)
    r.visit(node)
    return r


def span(n):
    return n.end_lineno - n.lineno + 1


def find_def(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name:
            return n
    return None


def note_loop(prep):
    """_prepare's largest top-level `for` over the notes: the row builder."""
    loops = [n for n in prep.body if isinstance(n, ast.For)]
    return max(loops, key=span) if loops else None


def flatten_ifs(body, depth, out, names, maxdepth=2):
    """The note loop's branches: every `if` down to maxdepth, with its test."""
    for n in body:
        if isinstance(n, ast.If):
            r = reads(n.test, names)
            whole = reads(n, names)
            out.append(dict(line=n.lineno, depth=depth, lines=span(n),
                            test=ast.unparse(n.test)[:110], test_reads=sorted(r.found),
                            emits=whole.emits, reads=len(whole.found)))
            if depth < maxdepth:
                flatten_ifs(n.body, depth + 1, out, names, maxdepth)
                flatten_ifs(n.orelse, depth + 1, out, names, maxdepth)
        elif isinstance(n, (ast.For, ast.While, ast.With, ast.Try)) and depth < maxdepth:
            for blk in ("body", "orelse", "finalbody"):
                flatten_ifs(getattr(n, blk, []) or [], depth + 1, out, names, maxdepth)


def survey_prepare(names):
    src = open(os.path.join(HERE, "blockrender.py")).read()
    tree = ast.parse(src)
    prep = find_def(tree, "_prepare")
    loop = note_loop(prep)
    rows = []
    for n in prep.body:
        kind = type(n).__name__
        if isinstance(n, ast.FunctionDef):
            kind = "def " + n.name
        elif isinstance(n, ast.For):
            kind = "for " + ast.unparse(n.target)[:40] + " in " + ast.unparse(n.iter)[:30]
        rows.append((span(n), n.lineno, kind, n))
    helpers = [r for r in rows if r[2].startswith("def ")]
    loops = [r for r in rows if r[2].startswith("for ")]
    other = [r for r in rows if not r[2].startswith(("def ", "for "))]
    branches = []
    flatten_ifs(loop.body, 0, branches, names)
    total = reads(prep, names)
    in_loop = reads(loop, names)
    helper_emits = sum(reads(r[3], names).emits for r in helpers)
    return dict(prep=prep, loop=loop, rows=rows, helpers=helpers, loops=loops, other=other,
                branches=branches, total=total, in_loop=in_loop, helper_emits=helper_emits,
                lines=span(prep))


def module_reads(path, names, extra_vars=()):
    tree = ast.parse(open(os.path.join(HERE, path)).read())
    r = Reads(names, VOICE_VARS | set(extra_vars))
    r.visit(tree)
    # and string reads on any object: getattr(x, 'field') -- live reaches the
    # class through many names (self.pc, tmpl's, part.patch...)
    s = open(os.path.join(HERE, path)).read()
    for m in re.finditer(r"""(?:getattr|hasattr)\([^,()]+,\s*['"](\w+)['"]""", s):
        if m.group(1) in names:
            r.found[m.group(1)] += 1
    for m in re.finditer(r"""\.(\w+)\b""", s):
        if m.group(1) in names and len(m.group(1)) > 3:
            r.found[m.group(1)] += 0        # seen as an attribute somewhere (weak)
    return r


def survey_live():
    tree = ast.parse(open(os.path.join(HERE, "live.py")).read())
    out = []
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            meths = [m for m in n.body if isinstance(m, ast.FunctionDef)]
            out.append((span(n), n.name, len(meths),
                        sorted(((span(m), m.name) for m in meths), reverse=True)[:6]))
        elif isinstance(n, ast.FunctionDef):
            out.append((span(n), n.name + "()", 0, []))
    return sorted(out, reverse=True)


def templates():
    """A sample of live templates: rows, columns, bytes, build time."""
    import numpy as np
    import live
    sample = ((0, False), (19, False), (24, False), (33, False), (40, False), (48, False),
              (56, False), (73, False), (80, False), (88, False), (0, True))
    out = []
    for prog, drums in sample:
        p = live.Patch(prog, drums, "hybrid440")
        with live.quiet():
            vdep = p._vel_dependent()
        for note in ((36, 38, 42, 46, 49) if drums else (24, 36, 48, 60, 72, 84, 96)):
            t = time.time()
            with live.quiet():
                tm = p._raw_template(note, 100)
            dt = time.time() - t
            cols = {k: v for k, v in tm.items() if isinstance(v, np.ndarray)}
            out.append(dict(prog=prog, drums=drums, note=note, vel_dependent=vdep, rows=int(tm.get("P") or 0),
                            cols=len(cols), bytes=int(sum(v.nbytes for v in cols.values())),
                            f64=int(sum(v.nbytes for v in cols.values() if v.dtype == np.float64)),
                            ms=dt * 1e3))
    return out


def main(argv):
    jpath = argv[argv.index("--json") + 1] if "--json" in argv else None
    fields, methods, voices, SV = voice_names()
    names = fields | methods
    P = survey_prepare(names)

    print("PREPARE blockrender._prepare: %d lines, one function" % P["lines"])
    print("        %d nested helpers (%d lines, %d emit_partial calls), %d top-level loops, %d other statements"
          % (len(P["helpers"]), sum(r[0] for r in P["helpers"]), P["helper_emits"], len(P["loops"]), len(P["other"])))
    print("        biggest helpers: " + ", ".join("%s %d" % (r[2][4:], r[0]) for r in sorted(P["helpers"], reverse=True)[:10]))
    print("        loops: " + "; ".join("@%d %d lines: %s" % (r[1], r[0], r[2]) for r in sorted(P["loops"], reverse=True)[:8]))
    print("        the note loop @%d: %d lines, %d emit_partial calls, reads %d voice names (%d reads)"
          % (P["loop"].lineno, span(P["loop"]), P["in_loop"].emits, len(P["in_loop"].found), sum(P["in_loop"].found.values())))
    print("        all of _prepare reads %d voice names (%d fields, %d methods)"
          % (len(P["total"].found), len(set(P["total"].found) & fields), len(set(P["total"].found) & methods)))

    br = P["branches"]
    gated = [b for b in br if b["test_reads"]]
    print("\nBRANCHES the note loop's `if`s to depth 2: %d; %d test a voice feature" % (len(br), len(gated)))
    print("        the largest that do (lines, emit_partial calls, test):")
    for b in sorted(gated, key=lambda b: -b["lines"])[:30]:
        print("        %5d %3d  @%d  %s" % (b["lines"], b["emits"], b["line"], b["test"]))
    feat = collections.Counter(f for b in gated for f in b["test_reads"])
    print("        features tested most: " + ", ".join("%s %d" % kv for kv in feat.most_common(20)))

    # who reads what
    body_reads = set()
    seen = set()
    for k in SV.tree_classes(voices):
        for name, val in vars(k).items():
            if isinstance(val, SV.FUNC_KINDS):
                fn = SV.func_of(val)
                if fn is not None and fn not in seen:
                    seen.add(fn)
                    body_reads |= set(fn.__code__.co_names) & fields
    L = module_reads("live.py", names, ("tmpl", "p", "patch"))
    # anywhere at all: getattr(any, 'name') or any.name, in every module of the
    # repo (a distinctive name -- with an underscore -- so `gain` on some
    # other object does not count), or vars(k).get('name') as the
    # __init_subclass__ hooks read
    anywhere = set()
    for path in sorted(os.listdir(HERE)):
        if not path.endswith(".py"):
            continue
        s = open(os.path.join(HERE, path)).read()
        for m in re.finditer(r"""(?:getattr|hasattr)\([^,()]+,\s*['"](\w+)['"]|\.get\(\s*['"](\w+)['"]|\.(\w+)\b""", s):
            nm = m.group(1) or m.group(2) or m.group(3)
            if nm in fields and (m.group(1) or m.group(2) or "_" in nm.strip("_")):
                anywhere.add(nm)
    by_prep = set(P["total"].found)
    by_live = {n for n, c in L.found.items() if c}
    print("\nFEATURES %d voice fields: %d read by _prepare, %d by live, %d by the voice bodies"
          % (len(fields), len(by_prep & fields), len(by_live & fields), len(body_reads)))
    nowhere = sorted(fields - by_prep - by_live - body_reads - anywhere)
    print("        read nowhere in the repo (as .name, getattr, or .get('name')): %d -- dead, or built by string" % len(nowhere))
    print("          " + ", ".join(nowhere[:80]))
    only_live = sorted((by_live & fields) - by_prep - body_reads)
    print("        read by live only (live's own behaviour, beyond templates): %d: %s" % (len(only_live), ", ".join(only_live[:40])))

    lv = survey_live()
    tot = sum(r[0] for r in lv)
    print("\nLIVE    live.py's top level: %d lines in classes and functions" % tot)
    for n, name, nm, top in lv[:12]:
        print("        %6d  %-24s %3d methods; biggest: %s" % (n, name, nm, ", ".join("%s %d" % (b, a) for a, b in top[:5])))

    T = None
    if "--templates" in argv:
        T = templates()
        print("\nTEMPLATES (velocity 100, hybrid440)")
        for t in T:
            print("        prog %3d%s note %3d: %5d rows, %2d cols, %7.1f kB (%2.0f%% float64), %5.1f ms%s"
                  % (t["prog"], "d" if t["drums"] else " ", t["note"], t["rows"], t["cols"], t["bytes"] / 1e3,
                     100.0 * t["f64"] / max(1, t["bytes"]), t["ms"], "  vel-dependent" if t["vel_dependent"] and t["note"] in (24, 36) else ""))
        mel = [t for t in T if not t["drums"]]
        mean = sum(t["bytes"] for t in mel) / len(mel)
        print("        mean %.0f kB a melodic note; a program over 128 keys %.1f MB per velocity band;"
              % (mean / 1e3, 128 * mean / 1e6))
        print("        the 128 capitals %.2f GB a band, + %d variations %.1f GB a band (before float32/compression)"
              % (128 * 128 * mean / 1e9, len(__import__("patch_map").VARIATIONS),
                 len(__import__("patch_map").VARIATIONS) * 128 * mean / 1e9))

    if jpath:
        with open(jpath, "w") as f:
            json.dump(dict(prepare_lines=P["lines"],
                           helpers=[(r[2][4:], r[1], r[0]) for r in P["helpers"]],
                           branches=P["branches"],
                           reads_prepare=dict(P["total"].found), reads_live={k: v for k, v in L.found.items() if v},
                           body_reads=sorted(body_reads), nowhere=nowhere, templates=T), f, indent=1)
        print("\n  " + jpath)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
