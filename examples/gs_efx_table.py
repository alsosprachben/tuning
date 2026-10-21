#!/usr/bin/env python3
"""The SC-88Pro's insertion effects, read off Roland's own data table.

    python3 examples/gs_efx_table.py SC-88PRO_OM.pdf [gs_efx_params.py]

The owner's manual (Chapter 8, "Effect list", PDF pages 178-184) gives every
one of the 64 types its MSB/LSB and its parameters 1-20: name, range, the
default between the range's ends where it prints one ("0 - 80 - 127"), the
value encoding, and the address (03H-16H); its "Effect data table" (PDF
pages 185-186) gives the fourteen value tables (*1 Pre Delay ... *14 Accl)
those encodings name. The pages are two columns, so each is read as its two
halves (pdftotext -x/-W), not split in the text.

Writes gs_efx_params.py: TYPES {(msb, lsb): (number, name)}, PARAMS
{name: {n: (param, range, default as printed, raw default 0-127 or None,
encoding)}}, VALUE_TABLES {k: [128 values]}. A raw default is worked out
from the encoding -- a linear range (00-7F, 34-4C about 40H, a percentage
2 % a step about 40H, L63-R63 about 40H) or the value table's first entry
equal to the printed one; a row that prints only its range, or a switch,
keeps None.
"""
import os
import re
import subprocess
import sys

TYPE_PAGES = range(178, 185)
TABLE_PAGES = (185, 186)
HALF = 298          # the A4 page's half width, points

_HEAD = re.compile(r"^\s*(\d+)\s*:\s*(.+?)\s{2,}([0-9A-F]{2})\s+([0-9A-F]{2})\s*$")
_ROW = re.compile(r"^\s*([+#])?\s*(\S.*?)\s{2,}(\S.*?)\s{2,}(\S.*?)\s{2,}([0-9A-F]{2})\s*$")
# ...and a row whose value runs into its encoding ("990m/1sec*3", "D 0<E 00 - 7F"):
# the encoding and the address found from the line's end
_ROW2 = re.compile(r"^\s*([+#])?\s*(\S.*?)\s{2,}(.*?)\s*(\*\d+|[0-9A-F]{2}\s*-\s*[0-9A-F]{2}"
                   r"|[0-9A-F]{2}(?:/[0-9A-F]{2})+)\s+([0-9A-F]{2})\s*$")


def _text(pdf, page, x, w):
    return subprocess.run(["pdftotext", "-q", "-f", str(page), "-l", str(page), "-layout",
                           "-x", str(x), "-y", "0", "-W", str(w), "-H", "842", pdf, "-"],
                          check=True, capture_output=True, text=True).stdout


def value_tables(pdf):
    """{1..14: [128 strings]}: the data table, its ditto marks filled in."""
    out = {k: [None] * 128 for k in range(1, 15)}
    last = [None] * 14
    for pg in TABLE_PAGES:
        for line in _text(pdf, pg, 0, 595).splitlines():
            f = line.split()
            if len(f) < 15 or not re.fullmatch(r"[0-9A-F]{2}", f[0]):
                continue
            v = int(f[0], 16)
            for k in range(14):
                x = f[1 + k]
                if x == '"':
                    x = last[k]
                last[k] = x
                out[k + 1][v] = x
    return out


def _num(s):
    s = s.strip().replace("%", "").replace("m", "").replace("k", "e3")
    try:
        return float(s)
    except ValueError:
        return None


def raw_default(rng, enc, default, tables):
    """The default as the 0-127 value the parameter's address takes, or None."""
    if default is None:
        return None
    m = re.fullmatch(r"\*(\d+)", enc.strip())
    if m:
        tab = tables.get(int(m.group(1)))
        if tab:
            want = default.strip()
            for i, x in enumerate(tab):
                if x is not None and (x == want or (_num(x) is not None and _num(x) == _num(want))):
                    return i
        return None
    lohi = re.fullmatch(r"([0-9A-F]{2})\s*-\s*([0-9A-F]{2})", enc.strip())
    if not lohi:
        return None
    lo, hi = int(lohi.group(1), 16), int(lohi.group(2), 16)
    d = default.strip()
    if d.startswith(("L", "R")) and d[1:].isdigit():               # L63 - 0 - R63
        return 0x40 + (int(d[1:]) if d[0] == "R" else -int(d[1:]))
    if d == "0" and rng.strip().startswith("L"):                    # ...its centre
        return 0x40
    if d == "D=E":                                                  # a balance's middle
        return 0x40
    m = re.fullmatch(r"D>(\d+)E", d)                                 # dry over the effect at x
    if m:
        return int(m.group(1)) // 2
    m = re.fullmatch(r"D(\d+)<E", d)                                 # the effect over the dry
    if m:
        return 127 - int(m.group(1)) // 2
    if "%" in d:                                                    # 2 % a step about 40H
        return 0x40 + int(round(_num(d) / 2.0))
    x = _num(d)
    if x is None:
        return None
    if (lo, hi) == (0x34, 0x4C) or (lo, hi) == (0x28, 0x58):        # signed about 40H
        return 0x40 + int(round(x))
    if (lo, hi) == (0, 0x7F) and rng.strip().startswith("0 "):      # 0 - 127 (or a part of it)
        return int(round(x))
    return None


def parse(pdf):
    tables = value_tables(pdf)
    types, params, cur = {}, {}, None
    for pg in TYPE_PAGES:
        for x, w in ((0, HALF), (HALF, 595 - HALF)):
            for line in _text(pdf, pg, x, w).splitlines():
                h = _HEAD.match(line)
                if h:
                    cur = h.group(2).strip()
                    types[(int(h.group(3), 16), int(h.group(4), 16))] = (int(h.group(1)), cur)
                    params[cur] = {}
                    continue
                r = _ROW.match(line) or _ROW2.match(line)
                if not (r and cur):
                    continue
                mark, name, rng, enc, addr = r.groups()
                n = int(addr, 16) - 2
                if not 1 <= n <= 20:
                    continue
                parts = [p.strip() for p in re.split(r"\s+-\s+", rng)]
                default = parts[1] if len(parts) == 3 else None
                params[cur][n] = (name.strip(), rng.strip(), default,
                                  raw_default(rng, enc, default, tables), enc.strip(), mark or "")
    # ROTARY MULTI is 03H 00H: the SC-88Pro's text and the SC-8850's text and
    # table all say so; this table's "02 0C" is a misprint (02H 0CH is no type)
    for wrong, right in CORRECTIONS.items():
        if wrong in types:
            types[right] = types.pop(wrong)
    return types, params, tables


# misprints in the data table, against the manual's own text and the SC-8850's
CORRECTIONS = {(0x02, 0x0C): (0x03, 0x00)}


def main(argv):
    pdf = argv[1]
    out = argv[2] if len(argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gs_efx_params.py")
    types, params, tables = parse(pdf)
    with open(out, "w") as fh:
        fh.write('"""The SC-88Pro insertion effects\' types, parameters and value tables, as\n'
                 'its owner\'s manual prints them (Chapter 8). GENERATED by\n'
                 'examples/gs_efx_table.py from the manual -- do not edit; fix the parser.\n\n'
                 'PARAMS[type][n] = (name, range, default as printed or None, the default as\n'
                 'its 0-127 value or None, encoding, "+"/"#" for effect control 1/2)."""\n\n')
        fh.write("TYPES = {\n")
        for k in sorted(types):
            fh.write("    (0x%02X, 0x%02X): %r,\n" % (k[0], k[1], types[k]))
        fh.write("}\n\nPARAMS = {\n")
        for nm in sorted(params, key=lambda n: next(v[0] for v in types.values() if v[1] == n)):
            fh.write("    %r: {\n" % nm)
            for n in sorted(params[nm]):
                fh.write("        %d: %r,\n" % (n, params[nm][n]))
            fh.write("    },\n")
        fh.write("}\n\nVALUE_TABLES = {\n")
        for k in sorted(tables):
            fh.write("    %d: %r,\n" % (k, tables[k]))
        fh.write("}\n")
    print("  %d types, %d parameters, %d value tables -> %s"
          % (len(types), sum(len(p) for p in params.values()), len(tables), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
