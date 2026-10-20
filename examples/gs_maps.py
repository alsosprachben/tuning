#!/usr/bin/env python3
"""The later GS maps, read from Roland's SC-88Pro owner's manual (its
instrument list, pp.154-162 printed: every tone in its own Native map, the
SC-88 map and the SC-55 map, side by side), against what we have built.

    python3 examples/gs_maps.py parse      the manual's list -> refs/roland/sc88pro_instruments.tsv
    python3 examples/gs_maps.py inventory  each map's tones: built, or what building them takes

THE SC-55 MAP OF A LATER MODULE IS THE SC-55mkII's, which has more variation
tones than the original SC-55 (whose owner's manual p.68 patch_map's
VARIATION_NAMES follows): so "missing from the SC-55 map" here can be a tone
the original never had.
"""
import csv
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

PDF = os.path.expanduser("~/Documents/refs/roland/SC-88PRO_OM.pdf")
TSV = os.path.expanduser("~/Documents/refs/roland/sc88pro_instruments.tsv")
PAGES = range(156, 164)          # the PDF's pages of the instrument list (printed 154-161)


def _words(page):
    """[(x, y, word)] of one PDF page (pdftotext -bbox)."""
    html = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-bbox", PDF, "-"],
                          capture_output=True, text=True).stdout
    out = []
    for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="[\d.]+">([^<]*)</word>', html):
        import html as _h
        out.append((float(m.group(1)), float(m.group(2)), _h.unescape(m.group(3))))
    return out


VOICE = re.compile(r"^\d[#*+]?$|^[#*+]$")


def parse():
    """BY WORD POSITION: each word to the column whose header it falls under
    (the headers' x on the page, two tables side by side). A word in a voices
    column that is not a count ("2", "1#", "*") runs over from the name to its
    right (DoorCreaking), so it is that name's."""
    rows = []
    last = None                 # the program a page's first rows continue
    for p in PAGES:
        W = _words(p)
        heads = sorted((x, y) for x, y, w in W if w == "PC")
        if not heads:
            continue
        # the columns of each table: PC, CC00, Native, Voices, SC88, Voices, SC55, Voices
        tables = []
        for hx, hy in heads:
            line = sorted((x, w) for x, y, w in W if abs(y - hy) < 2 and x >= hx - 1)
            names = [w for x, w in line]
            xs = [x for x, w in line]
            try:
                i = names.index("PC")
                cols = [xs[i], xs[names.index("CC00", i)], xs[names.index("Native", i)]]
                vi = names.index("Voices", i)
                cols += [xs[vi], xs[names.index("SC88", vi)]]
                vi2 = names.index("Voices", vi + 1)
                cols += [xs[vi2], xs[names.index("SC55", vi2)], xs[names.index("Voices", vi2 + 1)]]
            except ValueError:
                continue
            tables.append((hy, cols))
        tables.sort(key=lambda t: t[1][0])
        # each table spans to the next one's PC column
        bounds = [(t[1], (tables[k + 1][1][0] - 8) if k + 1 < len(tables) else 1e9) for k, t in enumerate(tables)]
        ys = sorted({round(y, 0) for x, y, w in W})
        # IN READING ORDER: the left table top to bottom, then the right. Rows
        # at the top of a table continue the program before it -- the left
        # table's, the last of the page before; the right table's, the LEFT
        # table's last on this page. Walking both at once by line seeded only
        # the left: the right's first rows had no program and were dropped
        # (SC-88Pro 30.9-30.25, Rock Rhythm among them, which Tokei plays)
        pcs = {}
        for k, (cols, xend) in enumerate(bounds):
            prev = last if k == 0 else pcs.get(k - 1, last)
            if prev is not None:
                pcs[k] = prev
            for y in ys:
                line = sorted((x, w) for x, yy, w in W if abs(yy - y) < 1.5)
                # (a PC can sit a little left of its header)
                ws = [(x, w) for x, w in line if cols[0] - 14 <= x < xend]
                if not ws:
                    continue
                cells = [[] for _ in range(8)]
                for x, w in ws:
                    c = max([j for j in range(8) if x >= cols[j] - 3] or [0])
                    if c in (3, 5, 7) and not VOICE.match(w) and c + 1 < 8:
                        c += 1
                    cells[c].append(w)
                nums = [w for w in cells[0] + cells[1] if re.match(r"^\d{3}$", w)]
                if not nums:
                    continue
                if len(nums) == 2:
                    pcs[k] = int(nums[0])
                    bank = int(nums[1])
                elif cells[0] and not cells[1] and len(nums) == 1 and cells[2]:
                    bank = int(nums[0])
                else:
                    bank = int(nums[-1])
                if k not in pcs or bank > 127 or "Chapter" in cells[2]:
                    continue                    # (a page's footer: "Chapter 8 ... 154")
                nat = " ".join(cells[2])
                s88 = " ".join(cells[4]) or "-----"
                s55 = " ".join(cells[6]) or "-----"
                rows.append((pcs[k] - 1, bank, nat, " ".join(cells[3]), s88, " ".join(cells[5]),
                             s55, " ".join(cells[7])))
        if pcs:
            last = pcs[max(pcs)]
    rows = sorted(set(rows))
    with open(TSV, "w") as f:
        f.write("program\tbank\tnative\tnative_voices\tsc88\tsc88_voices\tsc55\tsc55_voices\n")
        for r in rows:
            f.write("\t".join(str(v) for v in r) + "\n")
    print("  %d rows -> %s" % (len(rows), TSV))
    return rows


PDF8850 = os.path.expanduser("~/Documents/refs/roland/SC-8850_OM.pdf")
TSV8850 = os.path.expanduser("~/Documents/refs/roland/sc8850_instruments.tsv")
PAGES8850 = range(167, 186)      # the instrument list (each even page heads its key first)


def parse8850():
    """THE SC-8850's LIST, which sets ALL FOUR maps side by side -- SC-8850,
    SC-88Pro, SC-88, SC-55 -- one table per group, two to a page stacked, the
    same columns. So it is the SC-8850 map (bank select LSB 4) and a second,
    independent reading of the other three to check the SC-88Pro's against.
    Columns from each page's header words; the remarks between ("[Pro]",
    "[88]": the same sound as that map) and the legato mark ":" dropped."""
    rows = []
    pc = None
    for p in PAGES8850:
        html = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), "-bbox", PDF8850, "-"],
                              capture_output=True, text=True).stdout
        import html as _h
        W = [(float(a), float(b), _h.unescape(w)) for a, b, w in
             re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)"[^>]*>([^<]*)</word>', html)]
        # the HEADER is the CC00 line that names the maps (the key above the
        # table on an even page says "CC00" too)
        sc = {round(y) for x, y, w in W if w == "SC-8850"}
        heads = sorted(y for x, y, w in W if w == "CC00" and any(abs(y - z) < 2 for z in sc))
        if not heads:
            continue
        hy = heads[0]
        hx = {}
        vo = []
        for x, y, w in sorted(W):
            if abs(y - hy) < 2:
                if w in ("CC00", "PC", "SC-8850", "SC-88Pro", "SC-88", "SC-55"):
                    hx[w] = x
                elif w == "Voices":
                    vo.append(x)
        # name spans: from a map's header to its Voices column
        spans = [(hx["SC-8850"], vo[0] - 4), (hx["SC-88Pro"], vo[1] - 4),
                 (hx["SC-88"], vo[2] - 4), (hx["SC-55"], vo[3] - 4)]
        for y in sorted({round(y, 0) for x, y, w in W if y > hy + 4}):
            line = sorted((x, w) for x, yy, w in W if abs(yy - y) < 1.5)
            cc = [w for x, w in line if abs(x - hx["CC00"]) < 6 and re.match(r"^\d{3}$", w)]
            if not cc:
                continue
            pcs = [w for x, w in line if abs(x - hx["PC"]) < 6 and re.match(r"^\d{3}$", w)]
            if pcs:
                pc = int(pcs[0])
            if pc is None:
                continue
            names = []
            for a, b in spans:
                ws = [w for x, w in line if a - 2 <= x < b and w != ":"]
                names.append(" ".join(ws) or "-----")
            rows.append((pc - 1, int(cc[0])) + tuple(names))
    rows = sorted(set(rows))
    with open(TSV8850, "w") as f:
        f.write("program\tbank\tsc8850\tsc88pro\tsc88\tsc55\n")
        for r in rows:
            f.write("\t".join(str(v) for v in r) + "\n")
    print("  %d rows -> %s" % (len(rows), TSV8850))
    return rows


if __name__ == "__main__" and sys.argv[1] == "parse8850":
    parse8850()


def load():
    out = []
    for line in open(TSV).read().splitlines()[1:]:
        p, b, nat, nv, s88, v88, s55, v55 = line.split("\t")
        out.append(dict(program=int(p), bank=int(b), native=nat, sc88=s88, sc55=s55))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "parse":
        parse()


# THE SC-88 MAP'S TONES WE LACK, BY WHAT BUILDING THEM TAKES (read off their
# names and the SC-88Pro manual's grouping; a first sort, to be refined as each
# is built):
#   alias    one of our voices already, under another number
#   derived  a setting of one of ours: wide, dark, octave, layered, velocity-
#            switched, reversed, a detuned pair -- cheap
#   organ    a registration (drawbars, stops, the Leslie) of our organs
#   synth    a panel on the Moog, voiced by ear (Ben's Messenger to check)
#   refit    an articulation of an instrument we have, which wants fitting
#            to a reference of it (a mute, a slow bow, a soft or bright tone)
#   new      an instrument we have not modelled: wants references
KIND = {}
for _k, _keys in {
    "alias": "3.8 4.24 117.1 117.9 118.9 98.3",
    "derived": "0.8 0.16 1.8 2.1 2.2 2.8 4.16 5.16 6.16 6.24 11.8 12.8 24.16 24.24 25.9 31.16 "
               "48.9 48.11 48.16 48.24 49.10 52.8 55.10 60.16 62.16 63.16 63.17 98.5 98.18 98.19 "
               "99.2 99.3 99.5 102.3 102.4 102.5 104.2 119.1 119.8 119.9 119.16 119.17 119.24 119.25 "
               "120.3 120.4 120.6 123.3 124.7 126.6 14.9 104.1 15.1 30.18",
    "organ": "16.1 16.9 16.16 16.17 16.18 16.32 16.33 16.40 17.1 17.32 18.8 18.16 18.24 19.16 19.24 19.32",
    "synth": "35.4 38.1 38.9 38.10 38.16 39.1 39.2 39.3 39.9 39.16 39.17 39.18 39.19 50.1 54.8 55.16 "
             "62.1 62.9 63.1 80.1 80.2 80.3 80.4 80.5 80.6 80.8 81.1 81.2 81.3 81.4 81.5 81.6 81.7 81.8 "
             "81.16 82.1 82.2 84.8 86.1 87.1 87.2 88.1 89.1 89.2 89.3 89.4 90.1 91.1 93.1 93.2 95.1 95.8 "
             "95.9 95.10 96.1 96.2 96.8 97.1 97.2 97.8 98.1 98.2 98.4 98.6 98.7 98.8 98.9 98.16 98.17 "
             "99.1 99.4 99.6 101.1 101.2 102.1 102.2 102.6 103.1",
    "refit": "4.25 4.26 5.24 11.1 15.8 22.1 24.32 24.40 25.32 26.1 28.1 28.16 30.1 30.2 33.1 33.2 34.8 "
             "35.1 35.2 35.3 35.5 36.8 40.8 44.8 44.9 48.1 48.10 49.1 49.8 49.9 52.9 52.32 55.8 55.9 "
             "56.1 56.24 56.25 57.1 58.1 60.1 60.8 61.16 63.1 65.8 66.8 105.1 106.1 111.1 120.5 "
             "30.9 30.16 30.17 30.24 30.25",
    "new": "16.24 56.8 71.8 75.8 104.8 104.16 105.8 105.16 105.24 107.16 111.8 111.16 112.8 112.9 "
           "112.10 112.11 112.16 113.8 123.4 123.5 12.16 12.17 12.24",
}.items():
    for _t in _keys.split():
        _p, _b = _t.split(".")
        KIND[(int(_p), int(_b))] = _k


def inventory(out=None):
    """The maps' tones against ours, and the SC-88 map's missing ones sorted
    by KIND, as Markdown (to `out`, else printed)."""
    import patch_map as P
    R = load()

    def built(p, b):
        return b == 0 or ((p, b) in P.VARIATIONS and (p, b) in P.VARIATION_NAMES)
    L = ["# GS maps: what we have, and what the later ones would take\n",
         "From Roland's SC-88Pro owner's manual (its instrument list, every tone in its Native,",
         "SC-88 and SC-55 maps side by side; examples/gs_maps.py). The SC-55 map of a later",
         "module is the SC-55mkII's, a few dozen tones more than the original SC-55's we built.\n",
         "| map | tones | built | to do |", "|---|---|---|---|"]
    for col, name in (("sc55", "SC-55 map (mkII)"), ("sc88", "SC-88 map"), ("native", "SC-88Pro map")):
        ts = [r for r in R if r[col] not in ("-----", "", "+ -----")]
        nb = sum(built(r["program"], r["bank"]) for r in ts)
        L.append("| %s | %d | %d | %d |" % (name, len(ts), nb, len(ts) - nb))
    miss = [r for r in R if r["sc88"] not in ("-----", "", "+ -----") and not built(r["program"], r["bank"])]
    order = ("alias", "derived", "organ", "synth", "refit", "new")
    what = dict(alias="one of our voices, under another number",
                derived="a setting of one of ours (wide, dark, octave, layered, velocity, reversed)",
                organ="a registration of our organs (drawbars, stops, the Leslie)",
                synth="a Moog panel, voiced by ear",
                refit="an articulation of one we have, wanting a fit to a reference",
                new="an instrument we have not modelled, wanting references")
    L += ["", "## The SC-88 map's %d missing tones, by what they take\n" % len(miss),
          "| kind | count | what it takes |", "|---|---|---|"]
    for k in order:
        L.append("| %s | %d | %s |" % (k, sum(KIND.get((r["program"], r["bank"])) == k for r in miss), what[k]))
    unk = [r for r in miss if (r["program"], r["bank"]) not in KIND]
    if unk:
        L.append("| (unsorted) | %d | |" % len(unk))
    mk2 = {(r["program"], r["bank"]) for r in R if r["sc55"] not in ("-----", "", "+ -----")}
    for k in order + (None,):
        rs = [r for r in miss if KIND.get((r["program"], r["bank"])) == k]
        if not rs:
            continue
        L += ["", "### %s\n" % (k or "unsorted")]
        L.append(", ".join("%d.%d %s%s" % (r["program"], r["bank"], r["sc88"],
                                           " (mkII)" if (r["program"], r["bank"]) in mk2 else "")
                           for r in rs))
    # THE DRUM SETS (the manual's drum set list): the SC-55 map's 10 we have
    L += ["", "## Drum sets\n",
          "| map | sets | we have | to do |", "|---|---|---|---|",
          "| SC-55 map | 10 | 10 | -- |",
          "| SC-88 map | 14 | 8 of them (Standard 1, Room, Power, Electronic, Jazz, Brush, Orchestra, SFX; "
          "our TR-808 without the 909's sounds) | Standard 2, TR-808/909, Dance, Ethnic, Kick & Snare, Rhythm FX |",
          "| SC-88Pro map | 25 | as above | and Standard 3 (each hit varied in timbre and timing), Hip Hop, "
          "Jungle, Techno, CR-78, TR-606, TR-707, TR-909, Asia, Cymbal & Claps, Rhythm FX 2 |"]
    s = "\n".join(L) + "\n"
    if out:
        open(out, "w").write(s)
    else:
        print(s)
    return s


if __name__ == "__main__" and sys.argv[1] == "inventory":
    inventory(sys.argv[2] if len(sys.argv) > 2 else None)


def write_names(path=os.path.join(HERE, "gs_map_names.py")):
    """gs_map_names.py: each map's variation tones by name, for patch_map's
    map switch (bank select LSB). Names only -- Roland's list, a fact about
    the modules -- so the renderers need no copy of the manual. From the
    SC-8850's list, which sets all four maps side by side and agrees with the
    SC-88Pro manual's tone for tone (parse8850)."""
    R = list(csv.reader(open(TSV8850), delimiter="\t"))[1:]
    L = ['"""THE SOUND CANVAS MAPS\' VARIATION TONES, by name: {map: {(program, bank):',
         'name}} -- bank select LSB 1 the SC-55 map (the SC-55mkII\'s, as a later',
         'module has it), 2 the SC-88 map, 3 the SC-88Pro\'s, 4 the SC-8850\'s. From',
         'the SC-8850 owner\'s manual\'s instrument list (all four maps side by side) by',
         'examples/gs_maps.py names; do not edit. Capitals (bank 0) are not listed."""', "",
         "MAP_NAMES = {"]
    for m, col in ((1, 5), (2, 4), (3, 3), (4, 2)):
        L.append("    %d: {" % m)
        for r in R:
            if int(r[1]) and r[col] not in ("-----", "", "+ -----"):
                L.append("        (%d, %d): %r," % (int(r[0]), int(r[1]), r[col].lstrip("+ ").strip()))
        L.append("    },")
    L.append("}")
    open(path, "w").write("\n".join(L) + "\n")
    print("  wrote %s" % path)


if __name__ == "__main__" and sys.argv[1] == "names":
    write_names()
