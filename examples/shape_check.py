#!/usr/bin/env python3
"""THE SHAPING PASS'S CHECK (nui/shape.h): each case's text shaped by the C++
pass, against the codepoints a reader expects to see drawn, left to right.

usage: python3 examples/shape_check.py [SCRATCH]   (SCRATCH: where the test
program is built; a temporary folder otherwise)
"""
import os, shutil, subprocess, sys, tempfile

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
    # THAI: sara am split, its circle a mark under the tone mark
    ("Thai sara am", "น้ำ", u(0x0E19, 0x0E49, 0x0E4D, 0x0E32)),
    ("Thai unchanged", "ดนตรี", "ดนตรี"),
    # DEVANAGARI: half forms at U+E900 + offset, reph U+E980, rakaar U+E981, ligatures U+E9A0..
    ("Devanagari half form", "नमस्ते", u(0x928, 0x92E, 0xE938, 0x924, 0x947)),
    ("Devanagari short i before its consonant", "हिन्दी", u(0x93F, 0x939, 0xE928, 0x926, 0x940)),
    ("Devanagari short i before a whole cluster", "स्थिति", u(0x93F, 0xE938, 0x925, 0x93F, 0x924)),
    ("Devanagari short i alone", "पियानो", u(0x93F, 0x92A, 0x92F, 0x93E, 0x928, 0x94B)),
    ("Devanagari reph", "धर्म", u(0x927, 0x92E, 0xE980)),
    ("Devanagari rakaar", "प्रेम", u(0x92A, 0xE981, 0x947, 0x92E)),
    ("Devanagari ksha", "क्षमा", u(0xE9A0, 0x92E, 0x93E)),
    ("Devanagari no half form: virama", "विद्या", u(0x93F, 0x935, 0x926, 0x94D, 0x92F, 0x93E)),
    ("Devanagari anusvara", "संगीत", u(0x938, 0x902, 0x917, 0x940, 0x924)),
]

# THE CROSS-CHECK (when HarfBuzz's hb-shape is installed: libharfbuzz-bin): words
# shaped by HarfBuzz with Noto fonts, its glyph names read back as the code
# points code7 draws -- Noto Sans Arabic names its glyphs by presentation form;
# Noto Serif Devanagari by the characters a conjunct joins
HB_ARABIC = ["سلام عليكم", "عربي", "موسيقى", "بيانو", "أغنية", "مرحبا بكم", "الموسيقى العربية", "كمان",
             "قانون", "عود", "طبلة", "ناي", "فلسطين", "مصر", "بغداد", "پیانو", "گیتار", "موسیقی"]
HB_DEVA = ["हिन्दी", "स्थिति", "धर्म", "प्रेम", "नमस्ते", "क्षमा", "विद्या", "पियानो", "संगीत", "कर्ता", "शास्त्रीय",
           "राग", "तबला", "सितार", "भारत", "गायक", "ज्ञान", "मुम्बई", "कृष्ण", "श्री", "पंडित", "उस्ताद"]
NO_HALF = {0x919, 0x91B, 0x91F, 0x920, 0x921, 0x922, 0x926, 0x939, 0x930, 0x931, 0x95C, 0x95D}
LIGS = {(0x915, 0x937): 0xE9A0, (0x91C, 0x91E): 0xE9A1, (0x924, 0x930): 0xE9A2, (0x936, 0x930): 0xE9A3}

def hb(font, word):
    out = subprocess.run(["hb-shape", "--no-positions", "--no-clusters", font, word], capture_output=True, text=True).stdout
    return out.strip().strip("[]").split("|")

def name_cps(name):
    name = name.split(".")[0]
    if not name.startswith("uni"):
        return None
    h = name[3:]
    return [int(h[i:i + 4], 16) for i in range(0, len(h), 4)]

def deva_from_hb(names):
    """HarfBuzz's Devanagari glyphs as code7 draws them: a conjunct HarfBuzz has as one
    glyph code7 draws as half forms (or a visible virama), the rakaar a mark"""
    o = []
    for n in names:
        c = name_cps(n)
        if c is None:
            return None
        if len(c) == 1:
            o += c
            continue
        # (consonants joined by viramas)
        cons = [x for x in c if x != 0x94D]
        if c == [0x930, 0x94D]:
            o.append(0xE980)
            continue
        k = 0
        while k < len(cons):
            if k + 1 < len(cons) and (cons[k], cons[k + 1]) in LIGS:
                o.append(LIGS[(cons[k], cons[k + 1])])
                k += 2
                if k < len(cons):
                    o.append(0x94D)
                continue
            if k + 1 < len(cons) and cons[k + 1] == 0x930:
                o += [cons[k], 0xE981]
                k += 2
                continue
            if k + 1 == len(cons):
                if c[-1] == 0x94D:
                    o += [cons[k]] if cons[k] in NO_HALF else [0xE900 + cons[k] - 0x900]
                else:
                    o.append(cons[k])
            elif cons[k] in NO_HALF:
                o += [cons[k], 0x94D]
            else:
                o.append(0xE900 + cons[k] - 0x900)
            k += 1
    return o

ARABIC_ISOL = {}
def arabic_from_hb(names):
    o = []
    for n in names:
        if n == "space":
            o.append(0x20)
            continue
        c = name_cps(n)
        if c is None or len(c) != 1:
            return None
        o.append(ARABIC_ISOL.get(c[0], c[0]))
    return o

def hb_cases():
    import re
    tab = open(os.path.join(HERE, "nui", "shape_tables.inc")).read()
    for m in re.finditer(r"\{0x([0-9A-F]+), '.', 0x([0-9A-F]+),", tab):
        ARABIC_ISOL[int(m.group(1), 16)] = int(m.group(2), 16)
    cases = []
    ar = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"
    dv = "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf"
    for font, words, conv in ((ar, HB_ARABIC, arabic_from_hb), (dv, HB_DEVA, deva_from_hb)):
        if not os.path.exists(font):
            continue
        for w in words:
            v = conv(hb(font, w))
            if v is not None:
                cases.append(("HarfBuzz: " + w, w, "".join(chr(x) for x in v)))
    return cases

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, "shape_test.cpp")
    exe = os.path.join(d, "shape_test")
    with open(src, "w") as f:
        f.write('#include "shape.h"\n#include <cstdio>\n#include <iostream>\n'
                'int main(){std::string l; while(std::getline(std::cin,l)) std::cout<<nui::shape(l)<<"\\n";}\n')
    subprocess.run(["g++", "-std=c++17", "-O1", "-I", os.path.join(HERE, "nui"), src, "-o", exe], check=True)
    cases = CASES + (hb_cases() if shutil.which("hb-shape") else [])
    if not shutil.which("hb-shape"):
        print("(hb-shape not installed: no HarfBuzz cross-check)")
    inp = "".join(c[1] + "\n" for c in cases)
    out = subprocess.run([exe], input=inp.encode(), capture_output=True, check=True).stdout.decode().split("\n")
    bad = 0
    for (what, logical, want), got in zip(cases, out):
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
