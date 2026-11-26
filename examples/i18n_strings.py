#!/usr/bin/env python3
"""THE INTERFACE'S TEXTS AND THEIR TRANSLATIONS (nui/i18n.h).

usage: python3 examples/i18n_strings.py [--write] [--lint] [--lang=xx] [--long]

  - the catalogue: every T("..."), TF("...") and N_("...") in nui/ (adjacent
    literals joined, escapes read), written by --write to ui/lang/strings.txt
    (one English text a line, JSON-quoted, with where it is used);
  - each table, ui/lang/<code>.json: the texts it lacks, the ones it has that
    the interface no longer uses, and any whose placeholders ({0} {1}, %d %s
    %.1f ...) differ from the English (a translation must keep them all, %
    ones in the same order); --long lists the ones much longer than their
    English (the boxes most likely to cut them);
  - --lint: literals in nui/ that look like text a player reads (a space
    between letters, or a word in capitals) and are not wrapped -- a text
    missed. A line that means to stay as it is says so: // i18n-skip

Exits 1 when a table lacks a text or a placeholder differs, or (--lint) when
anything unwrapped is found.
"""
import glob, json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUI = os.path.join(HERE, "nui")
LANG = os.path.join(HERE, "ui", "lang")

LIT = r'"(?:[^"\\]|\\.)*"'
CALL = re.compile(r'\b(T|TF|N_)\(\s*((?:' + LIT + r'\s*)+)')


def unescape(lit):
    """A C string literal's text (adjacent literals already joined)."""
    out = bytearray()
    for m in re.finditer(LIT, lit):
        s = m.group(0)[1:-1]
        i = 0
        while i < len(s):
            c = s[i]
            if c != "\\":
                out += c.encode()
                i += 1
                continue
            n = s[i + 1]
            if n == "x":
                j = i + 2
                while j < len(s) and s[j] in "0123456789abcdefABCDEF":
                    j += 1
                out.append(int(s[i + 2:j], 16) & 0xFF)
                i = j
                continue
            out += {"n": b"\n", "t": b"\t", '"': b'"', "\\": b"\\", "'": b"'", "0": b"\0"}.get(n, n.encode())
            i += 2
    return out.decode("utf-8", "replace")


def sources():
    return sorted(glob.glob(os.path.join(NUI, "*.h")) + glob.glob(os.path.join(NUI, "*.cpp")))


# (the engine's messages the interface shows, marked N_() where the engine makes them)
ENGINE = ["fileplay.h", "module.h", "engine.cpp", "efxchain.cpp", "partmux.h"]


def catalogue():
    """English text -> the places it is used ("file:line")."""
    cat = {}
    for p in sources() + [os.path.join(HERE, "native", f) for f in ENGINE]:
        src = open(p, encoding="utf-8").read()
        for m in CALL.finditer(src):
            en = unescape(m.group(2))
            line = src.count("\n", 0, m.start()) + 1
            cat.setdefault(en, []).append("%s:%d" % (os.path.basename(p), line))
    return cat


PH = re.compile(r"\{\d\}|%[-+ #0]*\d*(?:\.\d+)?[a-zA-Z]")


def placeholders(s):
    curly = sorted(re.findall(r"\{\d\}", s))
    printf = [x for x in PH.findall(s) if not x.startswith("{")]
    return curly, printf


def check(cat, code, show_long):
    p = os.path.join(LANG, code + ".json")
    tab = json.load(open(p, encoding="utf-8"))
    tab = {k: v for k, v in tab.items() if not k.startswith("_")}
    missing = [en for en in cat if en not in tab or not tab[en]]
    obsolete = [k for k in tab if k not in cat]
    bad = []
    for en in cat:
        if en in tab and tab[en] and placeholders(en) != placeholders(tab[en]):
            bad.append(en)
    print("%s: %d texts, %d missing, %d obsolete, %d placeholder mismatches" % (code, len(cat), len(missing), len(obsolete), len(bad)))
    for en in bad:
        print("  PLACEHOLDERS %r -> %r" % (en, tab[en]))
    for en in missing[:20]:
        print("  missing %r (%s)" % (en, cat[en][0]))
    if len(missing) > 20:
        print("  ... %d more missing" % (len(missing) - 20))
    if show_long:
        for en in cat:
            t = tab.get(en)
            if t and len(en) >= 4 and len(t) > 1.4 * len(en) + 2:
                print("  LONG %r -> %r (%s)" % (en, t, cat[en][0]))
    return not missing and not bad


# (literals that look like text a player reads: words in capitals, or a space between letters)
TEXTY = re.compile(r"[A-Za-z]{2,}[ ·,.:;!?'-]+[A-Za-z]|^[A-Z][A-Z0-9 +&'./:-]*[A-Z]{2,}[A-Z0-9 +&'./:-]*$")
SKIP_LINE = re.compile(r'i18n-skip|#include|fprintf\(stderr|call\(a, |"\{\\"call|\.get\("|getenv\(|sess::load|load\("|\bstr\(&|num\(&|flag\(&|\.o\["|static_assert|NUI_[A-Z_]+')


def lint():
    found = 0
    for p in sources():
        if os.path.basename(p) in ("i18n.h", "shape.h", "shape_tables.inc", "bdf.h", "gfx_gl.cpp", "gfx_metal.mm", "sheet.h"):
            continue
        src = open(p, encoding="utf-8").read()
        lines = src.split("\n")
        # (the literals inside a T( TF( N_( -- across lines too)
        wrapped = set()
        for m in CALL.finditer(src):
            for mm in re.finditer(LIT, m.group(2)):
                wrapped.add(m.start(2) + mm.start())
        for m in re.finditer(LIT, src):
            if m.start() in wrapped:
                continue
            n = src.count("\n", 0, m.start())
            line = lines[n]
            col = m.start() - (src.rfind("\n", 0, m.start()) + 1)
            if line.lstrip().startswith("//") or "//" in line[:col] or SKIP_LINE.search(line):
                continue
            s = unescape(m.group(0))
            if re.fullmatch(r"[a-z0-9_]+:[a-z0-9_:]*", s):     # (a help key: "ct:routes")
                continue
            if "\\\"" in m.group(0) or not TEXTY.search(s):
                continue
            print("%s:%d: %s" % (os.path.basename(p), n + 1, m.group(0)[:90]))
            found += 1
    print("%d unwrapped text(s)" % found)
    return found == 0


def main(argv):
    opt = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    cat = catalogue()
    ok = True
    if opt.get("write"):
        os.makedirs(LANG, exist_ok=True)
        with open(os.path.join(LANG, "strings.txt"), "w", encoding="utf-8") as f:
            f.write("# The interface's English texts (examples/i18n_strings.py --write): one a line, JSON-quoted,\n"
                    "# then where it is used. A table, ui/lang/<code>.json, maps each to its translation.\n")
            for en in sorted(cat):
                f.write("%s\t%s\n" % (json.dumps(en, ensure_ascii=False), " ".join(cat[en][:3])))
        print("%d texts -> ui/lang/strings.txt" % len(cat))
    codes = [opt["lang"]] if opt.get("lang") else sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(LANG, "*.json")))
    for c in codes:
        ok = check(cat, c, opt.get("long")) and ok
    if opt.get("lint"):
        ok = lint() and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
