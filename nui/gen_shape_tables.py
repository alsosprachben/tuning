#!/usr/bin/env python3
"""THE SHAPING PASS'S TABLES (nui/shape_tables.inc, read by nui/shape.h), made
from Python's Unicode data: the canonical compositions code7 can draw (NFC for
names stored decomposed), the nonspacing marks (drawn over the letter before
them, zero width), the bidi classes that are not L, and Arabic's joining
types with their presentation forms (isolated, final, initial, medial).

usage: python3 nui/gen_shape_tables.py   (writes nui/shape_tables.inc)
"""
import os
import unicodedata as U

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shape_tables.inc")


def ranges(pred, lo=0, hi=0xFFFF):
    out, start = [], None
    for c in range(lo, hi + 2):
        ok = c <= hi and pred(c)
        if ok and start is None:
            start = c
        elif not ok and start is not None:
            out.append((start, c - 1))
            start = None
    return out


# COMPOSITIONS: base + mark -> one character, where NFC makes it (exclusions respected)
compose = []
for c in range(0x00C0, 0x3000):
    d = U.decomposition(chr(c))
    if not d or d.startswith("<"):
        continue
    parts = [int(x, 16) for x in d.split()]
    if len(parts) == 2 and U.normalize("NFC", chr(parts[0]) + chr(parts[1])) == chr(c):
        compose.append((parts[0], parts[1], c))
compose.sort()

# MARKS: Mn and Me (Mc are spacing: Devanagari's ा ी ो take a cell)
marks = ranges(lambda c: U.category(chr(c)) in ("Mn", "Me"))

# BIDI: every class but L (the default) and NSM (the marks, above)
CLS = {"R": 1, "AL": 2, "EN": 3, "AN": 4, "ES": 5, "ET": 6, "CS": 7}
def bidi(c):
    b = U.bidirectional(chr(c))
    if b in ("L", "NSM", "") or U.category(chr(c)) in ("Mn", "Me"):
        return 0
    return CLS.get(b, 8)                         # (8: a neutral -- WS, ON, B, S, BN, LRE ...)
bidi_r = []
start, cur = None, 0
for c in range(0, 0x10000 + 1):
    b = bidi(c) if c <= 0xFFFF else -1
    if b != cur:
        if cur > 0:
            bidi_r.append((start, c - 1, cur))
        start, cur = c, b

# ARABIC: joining type (R right-joining, D dual) and forms isolated, final, initial, medial
D, R = "D", "R"
def fb(first, t):      # (Presentation Forms-B/A: the forms consecutive from `first`)
    return (first, first + 1, first + 2 if t == D else 0, first + 3 if t == D else 0)
AR = {0x0621: ("U", (0xFE80, 0, 0, 0))}
for cp, first, t in [
    (0x0622, 0xFE81, R), (0x0623, 0xFE83, R), (0x0624, 0xFE85, R), (0x0625, 0xFE87, R),
    (0x0626, 0xFE89, D), (0x0627, 0xFE8D, R), (0x0628, 0xFE8F, D), (0x0629, 0xFE93, R),
    (0x062A, 0xFE95, D), (0x062B, 0xFE99, D), (0x062C, 0xFE9D, D), (0x062D, 0xFEA1, D),
    (0x062E, 0xFEA5, D), (0x062F, 0xFEA9, R), (0x0630, 0xFEAB, R), (0x0631, 0xFEAD, R),
    (0x0632, 0xFEAF, R), (0x0633, 0xFEB1, D), (0x0634, 0xFEB5, D), (0x0635, 0xFEB9, D),
    (0x0636, 0xFEBD, D), (0x0637, 0xFEC1, D), (0x0638, 0xFEC5, D), (0x0639, 0xFEC9, D),
    (0x063A, 0xFECD, D), (0x0641, 0xFED1, D), (0x0642, 0xFED5, D), (0x0643, 0xFED9, D),
    (0x0644, 0xFEDD, D), (0x0645, 0xFEE1, D), (0x0646, 0xFEE5, D), (0x0647, 0xFEE9, D),
    (0x0648, 0xFEED, R), (0x064A, 0xFEF1, D),
    # (Persian and Urdu, Forms-A)
    (0x0671, 0xFB50, R), (0x067E, 0xFB56, D), (0x0679, 0xFB66, D), (0x0686, 0xFB7A, D),
    (0x0688, 0xFB88, R), (0x0698, 0xFB8A, R), (0x0691, 0xFB8C, R), (0x06A9, 0xFB8E, D),
    (0x06AF, 0xFB92, D), (0x06BA, 0xFB9E, R), (0x06BE, 0xFBAA, D), (0x06C1, 0xFBA6, D),
    (0x06D2, 0xFBAE, R), (0x06CC, 0xFBFC, D)]:
    AR[cp] = (t, fb(first, t))
AR[0x0649] = (D, (0xFEEF, 0xFEF0, 0xFBE8, 0xFBE9))          # (alef maksura: its joining forms in Forms-A)
AR[0x0640] = ("C", (0, 0, 0, 0))                           # (tatweel: joins both sides, no forms)
# lam + alef -> the ligature (isolated, final)
LAMALEF = [(0x0622, 0xFEF5), (0x0623, 0xFEF7), (0x0625, 0xFEF9), (0x0627, 0xFEFB)]

# BRACKETS mirrored in a right-to-left run
MIRROR = [("(", ")"), ("[", "]"), ("{", "}"), ("<", ">"), ("«", "»"), ("‹", "›")]

with open(OUT, "w") as f:
    f.write("// made by nui/gen_shape_tables.py from Python %s's Unicode %s: do not edit\n"
            % (__import__("sys").version.split()[0], U.unidata_version))
    f.write("static const uint32_t SH_COMPOSE[][3] = {\n")
    for a, b, c in compose:
        f.write("    {0x%04X, 0x%04X, 0x%04X},\n" % (a, b, c))
    f.write("};\nstatic const uint32_t SH_MARK[][2] = {\n")
    for a, b in marks:
        f.write("    {0x%04X, 0x%04X},\n" % (a, b))
    f.write("};\n// (1 R, 2 AL, 3 EN, 4 AN, 5 ES, 6 ET, 7 CS, 8 neutral)\n")
    f.write("static const uint32_t SH_BIDI[][3] = {\n")
    for a, b, c in bidi_r:
        f.write("    {0x%04X, 0x%04X, %d},\n" % (a, b, c))
    f.write("};\n// (joining: 'U' none, 'R' right, 'D' dual, 'C' causing; forms isolated, final, initial, medial)\n")
    f.write("static const uint32_t SH_ARABIC[][6] = {\n")
    for cp in sorted(AR):
        t, fm = AR[cp]
        f.write("    {0x%04X, '%s', 0x%04X, 0x%04X, 0x%04X, 0x%04X},\n" % ((cp, t) + tuple(fm)))
    f.write("};\nstatic const uint32_t SH_LAMALEF[][2] = {\n")
    for a, l in LAMALEF:
        f.write("    {0x%04X, 0x%04X},\n" % (a, l))
    f.write("};\nstatic const uint32_t SH_MIRROR[][2] = {\n")
    for a, b in MIRROR:
        f.write("    {0x%04X, 0x%04X},\n    {0x%04X, 0x%04X},\n" % (ord(a), ord(b), ord(b), ord(a)))
    f.write("};\n")
print(OUT, len(compose), "compositions,", len(marks), "mark ranges,", len(bidi_r), "bidi ranges,", len(AR), "Arabic letters")
