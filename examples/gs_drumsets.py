#!/usr/bin/env python3
"""The Sound Canvas's drum sets, every key, from the SC-88 Pro owner's manual's
text layer ("Native Drum set (1-7)", "SC-88 Drum set (1-3)", "SC-55 Drum
set": printed pp.163-176).

    python3 -I examples/gs_drumsets.py parse MANUAL.txt OUT.tsv   (pdftotext -layout; the SC-88 Pro's
                                                                   manual, or the SC-8850's: "sc8850" rows)
    python3 -I examples/gs_drumsets.py diff OUT.tsv [SET ...]     each set's keys unlike Standard 1

Each page sets its sets side by side, one fixed-width column each, under a
"PC1 PC2 ..." line and a line of names; one text row per key, in key order,
its number at the left -- or, for some rows, on a line of its own after it,
which is skipped (the key counts on). "←" is "same as Standard 1" (that map's),
"---" no sound; "[EXCn]" (exclusive class), "*" (two voices), "[88]"/"[55]"
(an older map's sound) are kept in a column of their own.
"""
import re
import sys

PAGE = re.compile(r"^\s*(Native|SC-88|SC-55|SC-8850) Drum [Ss]et(?: \((\d+)\))?\s*$")
PCROW = re.compile(r"PC\s?\d+")
PAIRED = re.compile(r"PC\s?(\d+)(?:\s*/\s*PC\s?(\d+))?")


def parse(path):
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    out = []          # (map, pc, set name, key, name, flags)
    i = 0
    while i < len(lines):
        m = PAGE.match(lines[i])
        if not m:
            i += 1
            continue
        mp = {"Native": "native", "SC-88": "sc88", "SC-55": "sc55", "SC-8850": "sc8850"}[m.group(1)]
        j = i + 1
        # the PC line, then the names
        while j < len(lines) and not PCROW.search(lines[j]):
            j += 1
        pcl = lines[j]
        # A COLUMN CAN HOLD TWO SETS: the SC-55 page's "PC 1 / PC 33" over
        # "STANDARD / JAZZ", its cells "Kick Drum2 / Jazz BD2" where the two
        # differ and one name where they do not -- one column, both sets
        cols = []
        for mm in PAIRED.finditer(pcl):
            pcs = [int(g) for g in mm.groups() if g]
            cols.append((mm.start(), pcs))
        names = lines[j + 1]
        sets = []
        for k, (c0, pcs) in enumerate(cols):
            c1 = cols[k + 1][0] if k + 1 < len(cols) else None
            nm = names[c0:c1].strip() if c1 else names[c0:].strip()
            nms = [x.strip() for x in nm.split(" / ")] if len(pcs) > 1 else [nm]
            for q, pc in enumerate(pcs):
                sets.append((pc, nms[min(q, len(nms) - 1)], c0, c1, q, len(pcs)))
        # pages 7 (the SC-88 Pro's) and the SC-8850's "Notes 0-21 and 95-127 are
        # as follows": their keys jump, so they are not numbered by counting
        if "Notes 0-19" in " ".join(lines[i:j]) or "are as follows" in " ".join(lines[i:j]):
            i = j + 2                            # page 7: the 0-19, 97-127 keys, sets grouped
            continue
        key = None
        kcol = cols[0][0]                        # key numbers live left of the first set
        for line in lines[j + 2:]:
            if ("PC    : Program Number" in line or PAGE.match(line) or line.lstrip().startswith("SC-8850 Drum Set (")
                    or ": Same as the percussion sound" in line or "Program Number (Drum Set" in line):
                break
            km = re.match(r"^\s*(?:C\d+\s+|C-1\s+)?(\d{1,3})\b", line[:kcol])
            body = line
            if km and line[km.end():].strip() == "":
                continue                         # a key number alone on its line
            # THE SC-8850's labels drift: a key's number can sit on the line of the
            # row after it (Asia's 29 on Gamelan Gong 6's line, losing Gong 5). Its
            # rows run in key order without gaps, so there the first label sets
            # the count and every row after it is the next key
            if km and (mp != "sc8850" or key is None):
                key = int(km.group(1))
            elif key is not None:
                key += 1
            else:
                continue
            if not any(line[c0:c1 or None].strip() for _pc, _n, c0, c1, _q, _m in sets):
                continue
            for pc, sname, c0, c1, q, npc in sets:
                cell = body[c0:c1].strip() if c1 else body[c0:].strip()
                if npc > 1:
                    parts = [x.strip() for x in cell.split(" / ")]
                    cell = parts[min(q, len(parts) - 1)]
                flags = " ".join(re.findall(r"\[EXC\d\]|\[RND\]|\[88\]|\[55\]|\*", cell))
                name = re.sub(r"\[EXC\d\]|\[88\]|\[55\]|\*", "", cell).strip()
                name = re.sub(r"\s{2,}", " ", name)
                out.append((mp, pc, sname, key, name or "---", flags))
        i = j + 2
    return out


def write(rows, path):
    with open(path, "w") as f:
        f.write("map\tpc\tset\tkey\tname\tflags\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")


def read(path):
    rows = []
    for line in open(path).read().split("\n")[1:]:
        if line:
            mp, pc, sname, key, name, flags = line.split("\t")
            rows.append((mp, int(pc), sname, int(key), name, flags))
    return rows


def diff(rows, want=()):
    """{(map, pc, set): {key: name}} -- each set's keys that are not "←"."""
    sets = {}
    for mp, pc, sname, key, name, flags in rows:
        if pc == 1:
            continue
        if want and sname not in want and str(pc) not in want:
            continue
        if name not in ("←", "<-", "<–"):
            sets.setdefault((mp, pc, sname), {})[key] = (name, flags)
    return sets


def main(argv):
    if argv[1] == "parse":
        rows = parse(argv[2])
        write(rows, argv[3])
        n = {}
        for r in rows:
            n.setdefault((r[0], r[1], r[2]), set()).add(r[3])
        for k in sorted(n):
            ks = sorted(n[k])
            print("  %-6s PC%-3d %-16s keys %d-%d (%d)" % (k[0], k[1], k[2], ks[0], ks[-1], len(ks)))
        return 0
    if argv[1] == "diff":
        for (mp, pc, sname), ks in sorted(diff(read(argv[2]), argv[3:]).items()):
            print("== %s PC%d %s: %d keys its own" % (mp, pc, sname, len(ks)))
            for key in sorted(ks):
                print("   %3d  %s %s" % (key, ks[key][0], ks[key][1]))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
