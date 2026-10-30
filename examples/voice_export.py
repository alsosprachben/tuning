#!/usr/bin/env python3
"""The voices, flattened for a native runtime: one record per voice class,
every constant resolved through its MRO, every method as the chain of bodies
the MRO would call.

    python3 examples/voice_export.py OUTDIR [--check]

writes
  OUTDIR/voices.json    the export (below)
  OUTDIR/voice_export.h enums for the fields, methods and bodies, so C/C++
                        indexes the records by name

THE SHAPE (examples/voice_export_survey.py measured it): 1605 voices but only
230 distinct method bodies and 675 constant names, 286 of which never vary.
So the tree is not ported as a tree:

  pool      every distinct constant value once; a record names pool entries
  default   the root's (SynthProperties) value of each field
  voices    [{name, bases, fields: {field: pool index} where it differs from
            the default, methods: chain index per method}]
  chains    a method's bodies in MRO order for one voice: [body, ...]. The
            first is what the voice calls; a body that calls super() calls
            the next. (Not per class: with mixins, the body after a given
            one depends on the voice's whole MRO.)
  bodies    [{method, owner, file, line, lines, super, self_reads,
            self_writes, globals, random, numpy}] -- the functions a port
            writes, once each
  maps      the program, variation and kit tables that name voices
            (patch_map, percussion_map), voices as indices

VALUES are JSON with tags for what JSON lacks: {"voice": i} a voice class,
{"class": name} another class, {"fn": name} a function, {"dict": [[k, v]...]}
a dict (keys may be numbers or tuples), {"array": [dtype, shape, data]}, and
{"property": body, "value": v} a computed attribute, evaluated on the class
where it reads only the class ("value" absent where it needs a note).
Tuples and lists both become arrays; floats round-trip exactly.

--check reads voices.json back and compares every voice's every field and
method chain against the live classes. It proves the flattening lost
nothing; whether a native ENGINE reproduces the sound is a separate test.

The routing that picks a voice for a note (patch_map.property_class_for_note:
splits, layers, ensembles) is code, not in this export.
"""
import collections
import hashlib
import inspect
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

import voice_export_survey as SV  # noqa: E402  (imports tonelib, patch_map, percussion_map)
import patch_map  # noqa: E402
import percussion_map  # noqa: E402

MAPS = ((patch_map, ("PROGRAM_CLASS", "VARIATIONS", "BOWED_SPLIT", "BRASS_SPLIT", "SOLO_SPLIT",
                     "DRONE_NOTES", "_HARPSI", "_MELODIC_SFX")),
        (percussion_map, ("PERCUSSION", "KITS", "_RING_CLASSES")))


def voice_names(voices):
    """Unique, stable names: module.qualname, and where import made two
    classes of one name (patch_map's melodic SFX, one per kit), a #k by a
    hash of what they hold, so the order does not depend on the run."""
    def sig(c):
        return hashlib.sha1(repr(sorted((k, repr(v)) for k, v in vars(c).items()
                                        if not k.startswith("__"))).encode()).hexdigest()
    base = collections.defaultdict(list)
    for c in voices:
        base["%s.%s" % (c.__module__, c.__qualname__)].append(c)
    out = {}
    for name, cs in base.items():
        if len(cs) == 1:
            out[cs[0]] = name
        else:
            for k, c in enumerate(sorted(cs, key=sig), 1):
                out[c] = "%s#%d" % (name, k)
    return out


class Encoder:
    def __init__(self, vindex, bindex):
        self.vindex = vindex            # voice class -> index
        self.bindex = bindex            # (owner, method) -> body index

    def __call__(self, v, owner_name=None, depth=0):
        if depth > 12:
            raise ValueError("too deep")
        if v is None or isinstance(v, (bool, str)):
            return v
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, np.generic):
            return v.item()
        if isinstance(v, np.ndarray):
            return {"array": [str(v.dtype), list(v.shape), v.ravel().tolist()]}
        if isinstance(v, type):
            if v in self.vindex:
                return {"voice": self.vindex[v]}
            return {"class": "%s.%s" % (v.__module__, v.__qualname__)}
        if isinstance(v, (tuple, list)):
            return [self(x, depth=depth + 1) for x in v]
        if isinstance(v, (set, frozenset)):
            return {"set": sorted((self(x, depth=depth + 1) for x in v), key=json.dumps)}
        if isinstance(v, dict):
            return {"dict": [[self(k, depth=depth + 1), self(x, depth=depth + 1)] for k, x in v.items()]}
        if callable(v):
            return {"fn": "%s.%s" % (getattr(v, "__module__", "?"), getattr(v, "__qualname__", repr(v)))}
        raise TypeError("cannot encode %s" % type(v).__name__)


def eval_property(cls, prop):
    """A property's value when it reads only the class: on a bare instance
    (no __init__), so anything a note would set is missing and raises."""
    try:
        return True, prop.fget(object.__new__(cls))
    except Exception:
        return False, None


def build():
    voices = SV.all_voices()
    tree = SV.tree_classes(voices)
    names = voice_names(voices)
    voices.sort(key=lambda c: names[c])
    vindex = {c: i for i, c in enumerate(voices)}

    method_names, field_names = set(), set()
    for k in tree:
        for name, val in vars(k).items():
            if name.startswith("__") and name not in ("__init__", "__init_subclass__"):
                continue
            (method_names if isinstance(val, SV.FUNC_KINDS) and not isinstance(val, property)
             else field_names).add(name)
    method_names, field_names = sorted(method_names), sorted(field_names)

    # bodies: every (owner, method) any voice's chain passes through
    chains_of = {}              # (voice, method) -> tuple of owners
    for v in voices:
        for m in method_names:
            ch = tuple(k for k in v.__mro__ if isinstance(vars(k).get(m), SV.FUNC_KINDS))
            if ch:
                chains_of[(v, m)] = ch
    for v in voices:            # a property is a body too
        for f in field_names:
            for k in v.__mro__:
                if f in vars(k):
                    if isinstance(vars(k)[f], property):
                        chains_of.setdefault((v, f), (k,))
                    break
    owners = sorted({(k, m) for (v, m), ch in chains_of.items() for k in ch},
                    key=lambda km: (km[1], km[0].__module__, km[0].__qualname__))
    bindex = {km: i for i, km in enumerate(owners)}
    enc = Encoder(vindex, bindex)

    bodies = []
    for k, m in owners:
        fn = SV.func_of(vars(k)[m])
        r = SV.body_reads(fn)
        try:
            line = inspect.getsourcelines(fn)[1]
            path = os.path.relpath(inspect.getsourcefile(fn), HERE)
        except (OSError, TypeError):
            line, path = None, None
        bodies.append(dict(method=m, owner="%s.%s" % (k.__module__, k.__qualname__),
                           property=isinstance(vars(k)[m], property),
                           file=path, line=line, lines=r["lines"],
                           super="super()" in (r["source"] or ""),
                           self_reads=sorted(r["self_reads"]), self_writes=sorted(r["self_writes"]),
                           globals=r["globals"], imports=sorted(r["imports"]),
                           random=r["random"], numpy=r["numpy"]))

    chain_list, chain_index = [], {}

    def chain_id(ch):
        key = tuple(bindex[(k, m)] for k, m in ch)
        if key not in chain_index:
            chain_index[key] = len(chain_list)
            chain_list.append(list(key))
        return chain_index[key]

    pool, pool_index = [], {}

    def pool_id(enc_val):
        key = json.dumps(enc_val, sort_keys=True)
        if key not in pool_index:
            pool_index[key] = len(pool)
            pool.append(enc_val)
        return pool_index[key]

    def field_value(v, f):
        val = inspect.getattr_static(v, f)
        if isinstance(val, property):
            owner = next(k for k in v.__mro__ if f in vars(k))
            ok, x = eval_property(v, val)
            out = {"property": bindex[(owner, f)]}
            if ok:
                out["value"] = enc(x)
            return out
        return enc(val)

    root = SV.ROOT
    default = {}
    for f in field_names:
        try:
            default[f] = pool_id(field_value(root, f))
        except AttributeError:
            pass

    recs = []
    for v in voices:
        fields = {}
        for f in field_names:
            try:
                p = pool_id(field_value(v, f))
            except AttributeError:
                continue
            if default.get(f) != p:
                fields[f] = p
        absent = [f for f in default if not _has(v, f)]
        methods = {m: chain_id([(k, m) for k in chains_of[(v, m)]])
                   for m in method_names if (v, m) in chains_of}
        recs.append(dict(name=names[v], bases=[names.get(b, "%s.%s" % (b.__module__, b.__qualname__))
                                               for b in v.__bases__],
                         fields=fields, absent=absent, methods=methods))

    maps = {}
    for mod, keys in MAPS:
        for key in keys:
            val = getattr(mod, key)
            if isinstance(val, dict):
                maps["%s.%s" % (mod.__name__, key)] = {"dict": [[enc(k), enc(x)] for k, x in val.items()]}
            else:
                maps["%s.%s" % (mod.__name__, key)] = enc(val)

    return dict(version=1, fields=field_names, methods=method_names, pool=pool, default=default,
                voices=recs, chains=chain_list, bodies=bodies, maps=maps)


def _has(v, f):
    try:
        inspect.getattr_static(v, f)
        return True
    except AttributeError:
        return False


def header(ex):
    def ident(s):
        return "".join(ch if ch.isalnum() else "_" for ch in s)
    out = ["/* generated by examples/voice_export.py -- do not edit */",
           "#ifndef VOICE_EXPORT_H", "#define VOICE_EXPORT_H", "",
           "#define VOICE_EXPORT_VERSION %d" % ex["version"],
           "#define VOICE_COUNT %d" % len(ex["voices"]), ""]
    for tag, names in (("VF", ex["fields"]), ("VM", ex["methods"])):
        out.append("enum {")
        out += ["    %s_%s = %d," % (tag, ident(n), i) for i, n in enumerate(names)]
        out += ["    %s_COUNT = %d" % (tag, len(names)), "};", ""]
    out.append("enum {    /* method__owner; the functions a port writes */")
    for i, b in enumerate(ex["bodies"]):
        out.append("    VB_%s__%s = %d,%s" % (ident(b["method"]), ident(b["owner"]), i,
                                             "    /* super() */" if b["super"] else ""))
    out += ["    VB_COUNT = %d" % len(ex["bodies"]), "};", "", "#endif", ""]
    return "\n".join(out)


def check(ex):
    """Decode every voice's every field from voices.json and compare it with
    the live class's attribute; and every method chain with the live MRO."""
    voices = SV.all_voices()
    names = voice_names(voices)
    order = [r["name"] for r in ex["voices"]]
    by_name = {names[c]: c for c in voices}
    bad = []
    if set(by_name) != set(order):
        bad.append("voice set differs: %d live, %d exported" % (len(by_name), len(order)))
        return report(ex, bad, 0)
    cls_of = [by_name[n] for n in order]

    def dec(e):
        if isinstance(e, list):
            return [dec(x) for x in e]
        if isinstance(e, dict):
            if "voice" in e:
                return cls_of[e["voice"]]
            if "dict" in e:
                return [[dec(k), dec(x)] for k, x in e["dict"]]
            if "set" in e:
                return sorted((dec(x) for x in e["set"]), key=repr)
            if "array" in e:
                return ("array",) + tuple(e["array"][:2]) + (e["array"][2],)
            if "class" in e or "fn" in e:
                return e
            raise ValueError(e)
        return e

    def norm(v):
        if isinstance(v, np.generic):
            return v.item()
        if isinstance(v, np.ndarray):
            return ("array", str(v.dtype), list(v.shape), v.ravel().tolist())
        if isinstance(v, type):
            return v if v in names else {"class": "%s.%s" % (v.__module__, v.__qualname__)}
        if isinstance(v, (tuple, list)):
            return [norm(x) for x in v]
        if isinstance(v, (set, frozenset)):
            return sorted((norm(x) for x in v), key=repr)
        if isinstance(v, dict):
            return [[norm(k), norm(x)] for k, x in v.items()]
        if callable(v) and not isinstance(v, (int, float, str, bool)) and v is not None:
            return {"fn": "%s.%s" % (getattr(v, "__module__", "?"), getattr(v, "__qualname__", repr(v)))}
        return v

    def same(a, b):
        if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
            return True
        if type(a) is not type(b) and not (isinstance(a, list) and isinstance(b, list)):
            return False
        if isinstance(a, list):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        if isinstance(a, tuple):
            return a[:3] == b[:3] and same(a[3], b[3])
        return a == b

    nval = 0
    for r, v in zip(ex["voices"], cls_of):
        for f in ex["fields"]:
            here = _has(v, f)
            if f in r["absent"] or not (f in r["fields"] or f in ex["default"]):
                if here:
                    bad.append("%s.%s missing from the export" % (r["name"], f))
                continue
            if not here:
                bad.append("%s.%s exported but not on the class" % (r["name"], f))
                continue
            e = ex["pool"][r["fields"].get(f, ex["default"].get(f))]
            val = inspect.getattr_static(v, f)
            nval += 1
            if isinstance(val, property):
                b = ex["bodies"][e["property"]]
                owner = next(k for k in v.__mro__ if f in vars(k))
                if b["owner"] != "%s.%s" % (owner.__module__, owner.__qualname__) or b["method"] != f:
                    bad.append("%s.%s: property body" % (r["name"], f))
                ok, x = eval_property(v, val)
                if ok != ("value" in e) or (ok and not same(dec(e["value"]), norm(x))):
                    bad.append("%s.%s: property value" % (r["name"], f))
                continue
            if not same(dec(e), norm(val)):
                bad.append("%s.%s: %.80r != %.80r" % (r["name"], f, dec(e), norm(val)))
        for m in ex["methods"]:
            live = [k for k in v.__mro__ if isinstance(vars(k).get(m), SV.FUNC_KINDS)]
            got = [ex["bodies"][i] for i in ex["chains"][r["methods"][m]]] if m in r["methods"] else []
            if [(b["owner"], b["method"]) for b in got] != [("%s.%s" % (k.__module__, k.__qualname__), m) for k in live]:
                bad.append("%s.%s: chain" % (r["name"], m))
            for b, k in zip(got, live):
                if SV.func_of(vars(k)[m]).__code__.co_firstlineno != b["line"]:
                    bad.append("%s.%s: body line" % (r["name"], m))
    return report(ex, bad, nval)


def report(ex, bad, nval):
    for s in bad[:20]:
        print("  " + s)
    print("  check: %d voices, %d field values decoded and compared, %d method chains: %d differences"
          % (len(ex["voices"]), nval, sum(len(r["methods"]) for r in ex["voices"]), len(bad)))
    return len(bad)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    out = args[0]
    os.makedirs(out, exist_ok=True)
    jpath = os.path.join(out, "voices.json")
    if "--check" in argv and os.path.exists(jpath):
        with open(jpath) as f:
            return 1 if check(json.load(f)) else 0
    ex = build()
    with open(jpath, "w") as f:
        json.dump(ex, f, separators=(",", ":"))
    with open(os.path.join(out, "voice_export.h"), "w") as f:
        f.write(header(ex))
    nprop = sum(b["property"] for b in ex["bodies"])
    print("  %d voices, %d fields (%d with a root default), %d methods, %d bodies (%d properties), %d chains"
          % (len(ex["voices"]), len(ex["fields"]), len(ex["default"]), len(ex["methods"]),
             len(ex["bodies"]), nprop, len(ex["chains"])))
    nf = [len(r["fields"]) for r in ex["voices"]]
    print("  pool %d values; a voice overrides %d fields (median), %d at most"
          % (len(ex["pool"]), sorted(nf)[len(nf) // 2], max(nf)))
    print("  %s (%.1f MB)" % (jpath, os.path.getsize(jpath) / 1e6))
    print("  %s" % os.path.join(out, "voice_export.h"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
