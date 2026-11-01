#!/usr/bin/env python3
"""Write native/tunertables.h: the tuners' raw material, from the Python.

    python3 examples/tuner_tables.py [OUT.h]

native/tuner.cpp computes blockrender.tuning_table(name) for any tuner name
-- `hybrid`, `hybrid440@D`, `hybridharm:466`, `raga:todi@c#:277` -- with no
Python at run time. What a tuner computes from its name (its reference
pitch, its stretch, a key it is moved to, the pure octaves and the mean
third of the hybrids, the extrapolation past a generator's range, a raga's
Sa) is code there; what it starts from is DATA here, read off the classes
themselves, so this file is the one place it is copied and Python stays the
oracle:

  the twelve-tone tuners   each class's A, stretch_interval and intervals
                           (tunelib: stretch, even, gm2, linear, linear5,
                           pyth, just, meantone, well, werckmeister, sankey,
                           linearwell, bechstein -- linearcomma's constants
                           and compute_intervals' spreads as they come out)
  the path generators      ../path/path.py's HybridNotes, HybridMeanNotes,
                           StretchedHelmholtzNotes, SpiralNotes, SemiNotes and
                           PATHNotes(True, True): each note's frequency as the
                           generator places it (no frequency: NAN)
  the path tuners          which generator each registry name reads, its A,
                           and whether it is the pure-octave or mean-third kind
  `dynamic`                the search tuner's whole-keyboard table (tunelib.
                           Tuner: a search, so its result, at its own pitch)
  the raga systems         ragas.SYSTEMS' cents, and RAGAS' names

Every double as a C++17 hex float, so the header holds Python's bits. Run it
again when path.py, tunelib or ragas change; examples/tuner_check.py says
whether the native tables still equal the Python's.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

TWELVE = ("stretch", "even", "gm2", "linear", "linear5", "pyth", "just", "meantone", "well", "werckmeister",
          "sankey", "linearwell", "bechstein")
GENERATORS = (("HybridNotes", ()), ("HybridMeanNotes", ()), ("StretchedHelmholtzNotes", ()), ("SpiralNotes", ()),
              ("SemiNotes", ()), ("PATHNotes", (True, True)))


def hx(x):
    return "NAN" if x is None or (isinstance(x, float) and math.isnan(x)) else float(x).hex()


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(HERE, "native", "tunertables.h")
    import midilib
    import tunelib as TL
    import ragas
    import blockrender as B
    assert TL.reference() is None, "tables are written at each tuner's own pitch"
    L = ["// tunertables.h -- WRITTEN BY examples/tuner_tables.py from tunelib, ../path/path.py,",
         "// linearcomma and ragas: the tuners' raw material, every double Python's own bits.",
         "// Do not edit; run the script again (examples/tuner_check.py checks the result).",
         "", "#ifndef NV_TUNERTABLES_H", "#define NV_TUNERTABLES_H", "", "#include <cmath>", "",
         "namespace nv {", "namespace tuner {", ""]
    # the twelve-tone tuners
    L.append("struct Twelve {\n    const char *name;\n    double A, stretch, iv[12];\n};")
    L.append("static const Twelve TWELVE[] = {")
    for name in TWELVE:
        cls = midilib.tuner_registry[name]
        t = cls()
        L.append("    {\"%s\", %s, %s, {%s}}," % (name, hx(cls.A), hx(t.stretch),
                                                ", ".join(hx(cls.intervals[k]) for k in range(12))))
    L.append("};\n")
    # the path generators
    pm = TL._load_path_module()
    L.append("struct Gen {\n    const char *name;\n    double f[150];      // NAN: no frequency\n};")
    L.append("static const Gen GEN[] = {")
    for gname, gargs in GENERATORS:
        g = getattr(pm, gname)(*gargs)
        fs = [getattr(n, "f", None) for n in g.notes]
        assert len(fs) == 150
        L.append("    {\"%s\", {%s}}," % (gname, ", ".join(hx(f) for f in fs)))
    L.append("};\n")
    # the path tuners
    L.append("// kind 0 the generator's table, 1 on pure octaves (HybridHarmonicTuner),\n"
             "// 2 the mean-third chains (HybridMeanTuner, no generator); A NAN: the generator's pitch")
    L.append("struct PathT {\n    const char *name, *gen;\n    double A;\n    int kind;\n};")
    L.append("static const PathT PATH[] = {")
    for name, cls in midilib.tuner_registry.items():
        if not (isinstance(cls, type) and issubclass(cls, TL.PathTuner)):
            continue
        kind = (2 if issubclass(cls, TL.HybridMeanTuner)
                else 1 if issubclass(cls, TL.HybridHarmonicTuner) else 0)
        gen = cls.generator_name or ""
        if kind != 2:
            assert (gen, tuple(cls.generator_args)) in GENERATORS, (name, gen)
        L.append("    {\"%s\", \"%s\", %s, %d}," % (name, gen, hx(cls.A), kind))
    L.append("};\n")
    # dynamic
    dyn = B.tuning_table("dynamic")
    L.append("// `dynamic` (tunelib.Tuner): its search's whole-keyboard table")
    L.append("static const double DYNAMIC[128] = {%s};\n" % ", ".join(hx(dyn.get(n)) for n in range(128)))
    # the ragas
    L.append("struct RagaSys {\n    const char *name;\n    double cents[12];\n};")
    L.append("static const RagaSys RAGA_SYSTEMS[] = {")
    for name in sorted(ragas.SYSTEMS):
        L.append("    {\"%s\", {%s}}," % (name, ", ".join(hx(c) for c in ragas.SYSTEMS[name]["cents"])))
    L.append("};")
    L.append("static const char *RAGAS[] = {%s};\n" % ", ".join("\"%s\"" % r for r in sorted(ragas.RAGAS)))
    L += ["}  // namespace tuner", "}  // namespace nv", "", "#endif", ""]
    with open(out, "w") as f:
        f.write("\n".join(L))
    print("tuner tables: %d twelve-tone, %d generators, %d path tuners, %d raga systems -> %s"
          % (len(TWELVE), len(GENERATORS), sum(1 for x in L if x.startswith("    {\"") and "\", \"" in x),
             len(ragas.SYSTEMS), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
