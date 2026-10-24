#!/usr/bin/env python3
"""The General MIDI 2 sound set, every program and bank, from the SC-8850
owner's manual's text layer ("GM 2 Instrument List", printed p.213, and the
GM 2 Drum Set List beside its last column).

    python3 -I examples/gm2_list.py MANUAL.txt OUT.tsv     (pdftotext -layout)
    python3 -I examples/gm2_list.py names OUT.tsv          write gm2_names.py from it

Two columns a page, under a "PC# CC32 Tone Name Voices" header each; a row
is [PC] CC32 name voices, PC only on a program's first bank. The drum set
page's right half is its drum list, not tones, and is skipped. Writes
program (0-based), bank select LSB (CC32 under MSB 121), Roland's tone name.
"""
import re
import sys

ROW = re.compile(r"^\s*(\d{1,3})?\s+(\d{1,2})\s+(\S.*?\S)\s+:?(\d)\s*$")     # ":2": a stray mark before some voices


def parse(path):
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    i0 = next(i for i, l in enumerate(lines) if l.strip() == "GM 2 Instrument List")
    out, pc = [], {0: None, 1: None}
    split = None
    for line in lines[i0 + 1:]:
        if "Drum Set List" in line and "PC#" in line:
            split = line.index("GM 2 Drum Set List")     # the right half is drums from here
            drums = True
        elif line.lstrip().startswith("PC#"):
            hs = [m.start() for m in re.finditer(r"PC#", line)]
            split = hs[1] - 2 if len(hs) > 1 else None
            drums = False
        if split is None:
            continue
        halves = [line[:split], line[split:]] if not locals().get("drums") else [line[:split]]
        for side, h in enumerate(halves):
            m = ROW.match(h)
            if not m:
                continue
            if m.group(1):
                pc[side] = int(m.group(1))
            if pc[side] is None:
                continue
            prog, lsb = pc[side] - 1, int(m.group(2))
            # THE MANUAL'S MISPRINT: program 119 prints LSB 1 twice (808 Tom,
            # Elec Perc); GM 2's Elec Perc is LSB 2. A repeated LSB in a program
            # is read as the next one up.
            while any(o[0] == prog and o[1] == lsb for o in out):
                lsb += 1
            out.append((prog, lsb, re.sub(r"\s{2,}", " ", m.group(3))))
        if out and out[-1][0] == 127 and "Explosion" in out[-1][2]:
            break
    return sorted(out)


def write_names(tsv, path):
    """gm2_names.py: GM 2's variation tones by name, for patch_map.gm2_bank --
    names only, so the renderers need no copy of the manual."""
    rows = [l.split("\t") for l in open(tsv).read().split("\n")[1:] if l]
    L = ['"""GENERAL MIDI 2\'S VARIATION TONES, by name: {(program, bank select LSB under',
         'MSB 121): Roland\'s tone name} -- from the SC-8850 owner\'s manual\'s "GM 2',
         'Instrument List" by examples/gm2_list.py names; do not edit. Each is a Sound',
         'Canvas tone of the same name (patch_map.gm2_bank). Capitals (LSB 0) are',
         'not listed."""', "", "GM2_NAMES = {"]
    for p, b, n in rows:
        if int(b):
            L.append("    (%d, %d): %r," % (int(p), int(b), n))
    L.append("}")
    open(path, "w").write("\n".join(L) + "\n")
    print("  wrote %s" % path)


def main(argv):
    if argv[1] == "names":
        import os
        write_names(argv[2], os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          "gm2_names.py"))
        return 0
    rows = parse(argv[1])
    with open(argv[2], "w") as f:
        f.write("program\tlsb\tname\n")
        for p, b, n in rows:
            f.write("%d\t%d\t%s\n" % (p, b, n))
    progs = {p for p, _b, _n in rows}
    print("%d tones over %d programs" % (len(rows), len(progs)))
    missing = sorted(set(range(128)) - progs)
    if missing:
        print("programs with no row:", missing)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
