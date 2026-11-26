#!/usr/bin/env python3
"""THE SHAPING PASS'S CHECK (nui/shape.h): each case's text shaped by the C++
pass, against the codepoints a reader expects to see drawn, left to right.

usage: python3 examples/shape_check.py [SCRATCH]   (SCRATCH: where the test
program is built; a temporary folder otherwise)
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def cps(s):
    return " ".join("%04X" % ord(c) for c in s)

def u(*xs):
    return "".join(chr(x) for x in xs)

CASES = [
    # (what it checks, logical text, visual text)
    ("ascii unchanged", "Track 5 - Prelude.mid", "Track 5 - Prelude.mid"),
    ("decomposed accent composed", "Cafe\u0301 Sen\u0303or", "Café Señor"),
    ("Vietnamese two marks", "e\u0302\u0301", "\u1EBF"),
    ("Hebrew reversed", "שלום", "םולש"),
    ("Hebrew then a number", "שלום 123", "123 םולש"),
    ("Hebrew inside Latin", "Track 5 - שיר.mid", "Track 5 - ריש.mid"),
    ("Hebrew brackets mirrored", "(שלום)", "(םולש)"),
    ("Hebrew points kept after their letters", "שָׁלוֹם", u(0x05DD, 0x05D5, 0x05B9, 0x05DC, 0x05E9, 0x05B8, 0x05C1)),
    ("Arabic joining, lam-alef", "سلام", u(0xFEE1, 0xFEFC, 0xFEB3)),
    ("Arabic joining", "عربي", u(0xFEF2, 0xFE91, 0xFEAE, 0xFECB)),
    ("Arabic with digits (AN)", "غرفة 12", "12 " + u(0xFE94, 0xFED3, 0xFEAE, 0xFECF)),
    ("Arabic inside Latin", "Song عربي.mid", "Song " + u(0xFEF2, 0xFE91, 0xFEAE, 0xFECB) + ".mid"),
    # (a number after Arabic is an Arabic number (W2): it joins the right-to-left run, left of it, as browsers show it)
    ("a number after Arabic in Latin", "Song عربي 2.mid", "Song 2 " + u(0xFEF2, 0xFE91, 0xFEAE, 0xFECB) + ".mid"),
    ("Arabic harakat transparent", "بَيت", u(0xFE96, 0xFEF4, 0xFE91, 0x064E)),
    ("Persian peh, gaf", "پگ", u(0xFB93, 0xFB58)),
    ("isolated hamza", "ء", u(0xFE80)),
    # (the line left to right, the interface's: a Hebrew name keeps its extension at the end)
    ("Hebrew name, extension at the end", "שלום עליכם.mid", "םכילע םולש.mid"),
    ("bracketed number beside Hebrew (N0)", "Track 5 - שיר (2).mid", "Track 5 - (2) ריש.mid"),
    ("Latin in brackets beside Hebrew", "שיר (live).mid", "ריש (live).mid"),
]

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, "shape_test.cpp")
    exe = os.path.join(d, "shape_test")
    with open(src, "w") as f:
        f.write('#include "shape.h"\n#include <cstdio>\n#include <iostream>\n'
                'int main(){std::string l; while(std::getline(std::cin,l)) std::cout<<nui::shape(l)<<"\\n";}\n')
    subprocess.run(["g++", "-std=c++17", "-O1", "-I", os.path.join(HERE, "nui"), src, "-o", exe], check=True)
    inp = "".join(c[1] + "\n" for c in CASES)
    out = subprocess.run([exe], input=inp.encode(), capture_output=True, check=True).stdout.decode().split("\n")
    bad = 0
    for (what, logical, want), got in zip(CASES, out):
        ok = got == want
        bad += not ok
        print("%-4s %s" % ("ok" if ok else "FAIL", what))
        if not ok:
            print("     want", cps(want))
            print("     got ", cps(got))
    print("%d failed" % bad)
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
