"""The compiler command lines, as this platform builds them.

Every native library here is built by a gcc (or g++) command written for
Linux. On macOS (the port ahead of iOS) the same command is run as Apple's
clang reads it: clang for gcc, OpenMP through Homebrew's libomp (clang has
the pragma but no runtime: -Xpreprocessor -fopenmp, -lomp at the link), no
-lmvec (glibc's vector maths; Apple's libm has none to name). On Linux the
command is returned as written, so nothing built there changes.
"""
import os
import re
import sys

DARWIN = sys.platform == "darwin"
OMP = os.environ.get("TUNING_LIBOMP", "/opt/homebrew/opt/libomp")


def cmd(c):
    """Command line c (a list) for this platform."""
    c = list(c)
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
