"""The compiler command lines, as this platform builds them.

Every native library here is built by a gcc (or g++) command written for
Linux. On macOS (the port ahead of iOS) the same command is run as Apple's
clang reads it: clang for gcc, OpenMP through Homebrew's libomp (clang has
the pragma but no runtime: -Xpreprocessor -fopenmp, -lomp at the link), no
-lmvec (glibc's vector maths; Apple's libm has none to name). On Linux the
command is returned as written, so nothing built there changes -- but for
the CPU target.

THE CPU TARGET is fixed, never -march=native (a build for this machine
alone; an app's must run on every machine of its kind): x86-64-v3 on x86-64
Linux (AVX2 and FMA: Haswell, Zen and after), Apple's M1 on arm64 macOS,
armv8.2-a on other arm64 -- every library alike, Python's and the native
engine's, so the two still do the same arithmetic. TUNING_MARCH sets
another (its value goes in as -march=). A change of target rebuilds every
library here (retarget: the stamp .build_target).
"""
import os
import re
import sys

DARWIN = sys.platform == "darwin"
HERE = os.path.dirname(os.path.abspath(__file__))


def _target():
    m = os.environ.get("TUNING_MARCH")
    if m:
        return ["-march=" + m]
    mach = os.uname().machine
    if mach in ("x86_64", "AMD64"):
        return ["-march=x86-64-v3"]
    if DARWIN:
        return ["-mcpu=apple-m1"]
    if mach in ("aarch64", "arm64"):
        return ["-march=armv8.2-a"]
    return []


TARGET = _target()


def retarget():
    """A change of CPU target (or the first build under one): every library
    built here removed, so each rebuilds under it (they are rebuilt by
    mtime, which a flag does not move). The objects of .nvbuild carry their
    command in their stamps and rebuild themselves."""
    import glob
    stamp = os.path.join(HERE, ".build_target")
    want = " ".join(TARGET)
    try:
        with open(stamp) as f:
            if f.read().strip() == want:
                return
    except OSError:
        pass
    for lib in glob.glob(os.path.join(HERE, "lib*.so")) + glob.glob(os.path.join(HERE, "lib*.dylib")):
        try:
            os.remove(lib)
        except OSError:
            pass
    with open(stamp, "w") as f:
        f.write(want + "\n")


retarget()                  # (at import: before any build looks at what is built)
OMP = os.environ.get("TUNING_LIBOMP", "/opt/homebrew/opt/libomp")


def cmd(c):
    """Command line c (a list) for this platform."""
    c = [t for a in c for t in (TARGET if a == "-march=native" else [a])]
    if not DARWIN:
        return c
    out, omp = [], False
    for a in c:
        if a == "gcc":
            out.append("clang")
        elif a == "g++":
            out.append("clang++")
        elif a == "-fopenmp":
            out += ["-Xpreprocessor", "-fopenmp", "-I" + os.path.join(OMP, "include")]
            omp = True
        elif a == "-lmvec":
            continue
        elif a == "-Wl,-rpath,$ORIGIN":            # (the executable's own directory: dyld's name for it)
            out.append("-Wl,-rpath,@executable_path")
        else:
            out.append(a)
    linking = "-c" not in c
    if linking and (omp or "-shared" in c):
        out += ["-L" + os.path.join(OMP, "lib"), "-lomp"]
    if linking:                                     # (nvlive's devices: native/macio.h)
        out += ["-framework", "CoreMIDI", "-framework", "AudioToolbox", "-framework", "CoreAudio",
                "-framework", "CoreFoundation", "-framework", "Metal", "-framework", "Foundation"]
    if "-shared" in c and "-o" in c:
        # a library's install name is the path it was written to -- here a
        # temporary one, moved after -- so it is named as it will be found:
        # by @rpath, under its final name (".PID.tmp" off)
        final = re.sub(r"\.\d+\.tmp$", "", os.path.basename(c[c.index("-o") + 1]))
        out += ["-Wl,-install_name,@rpath/" + final]
    return out
