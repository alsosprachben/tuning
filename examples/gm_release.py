#!/usr/bin/env python3
"""What do General MIDI sets do at note-off? The release, read from the
SoundFonts on this machine, and the consensus the plucked voices take.

    python3 examples/gm_release.py [PROGRAM ...]

NOTE-OFF STARTS A RELEASE, IT DOES NOT SILENCE. Roland GS (VE-GS Pro MIDI
Implementation, ~/Documents/refs/roland): a note-off starts the tone's
release envelope, whose length is a per-tone preset with only a relative
change (NRPN 1/102 = CC72, -64..+63). GM itself specifies no envelope. So the
consensus is what the sets do: four on disk (FluidR3, GeneralUser GS,
MuseScore General, TimGM6mb), each preset's volume-envelope release (SF2
generator 38, timecents, instrument plus preset offset) per sample zone; the
median zone per set, the median over the sets.

USED ONLY WHERE NO RECORDING HOLDS A RELEASED NOTE -- which, surveyed, is every
plucked voice here (the harp, kalimba, nylon guitar and bass pizz references
are all left to ring; steel and electric guitars, electric bass and choir
have none).

OUR SHAPE IS NOT THEIRS. An SF2 release is linear in dB, about 96 dB over R;
ours (the kernel's AMP) is a smoothstep fade of length L on the note's own
decay, -40 dB at 0.94 L. Matched where a note is heard to end, -40 dB:
L = (40/96) R / 0.94 = 0.443 R. Printed beside R.
"""
import glob
import os
import struct
import sys

SETS = (("FluidR3", "/usr/share/sounds/sf2/FluidR3_GM.sf2"),
        ("GeneralUser GS", os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")),
        ("MuseScore General", os.path.expanduser("~/Documents/refs/soundfonts/MuseScore_General.sf2")),
        ("TimGM6mb", (sorted(glob.glob("/snap/*/*/usr/share/sounds/sf2/TimGM6mb.sf2")) or [""])[-1]))
# the plucked strings (GM 15, 24-37, 45, 46, 104-108) and the voices (52-54)
PROGRAMS = (15,) + tuple(range(24, 38)) + (45, 46, 52, 53, 54) + tuple(range(104, 109))
L_PER_R = (40.0 / 96.0) / 0.94
REL, INST, SAMPLE = 38, 41, 53


def _chunks(b, off, end):
    while off < end:
        cid, sz = b[off:off + 4], struct.unpack("<I", b[off + 4:off + 8])[0]
        yield cid, off + 8, sz
        off += 8 + sz + (sz & 1)


def _recs(raw, fmt, n):
    return [struct.unpack(fmt, raw[i:i + n]) for i in range(0, len(raw), n)]


def _s16(v):
    return v - 65536 if v >= 32768 else v


def releases(path, programs):
    """{program: (preset name, median zone release s)} for bank 0."""
    b = open(path, "rb").read()
    d = None
    for cid, o, sz in _chunks(b, 12, len(b)):
        if cid == b"LIST" and b[o:o + 4] == b"pdta":
            d = {c.decode(): b[oo:oo + s] for c, oo, s in _chunks(b, o + 4, o + sz)}
    phdr = _recs(d["phdr"], "<20sHHHIII", 38)
    pbag, pgen = _recs(d["pbag"], "<HH", 4), _recs(d["pgen"], "<HH", 4)
    inst, ibag, igen = _recs(d["inst"], "<20sH", 22), _recs(d["ibag"], "<HH", 4), _recs(d["igen"], "<HH", 4)

    def gens(gen, bag, i):
        return {g[0]: g[1] for g in gen[bag[i][0]:bag[i + 1][0]]}
    out = {}
    for pi, h in enumerate(phdr[:-1]):
        name, prog, bank = h[0].split(b"\0")[0].decode("latin1"), h[1], h[2]
        if bank != 0 or prog not in programs:
            continue
        rels, pglob = [], {}
        for zb in range(h[3], phdr[pi + 1][3]):
            pg = gens(pgen, pbag, zb)
            if INST not in pg:
                pglob = pg
                continue
            prel = _s16(pg.get(REL, pglob.get(REL, 0)))
            ii, iglob = pg[INST], {}
            for zi in range(inst[ii][1], inst[ii + 1][1]):
                ig = gens(igen, ibag, zi)
                if SAMPLE not in ig:
                    iglob = ig
                    continue
                rels.append(2.0 ** ((_s16(ig.get(REL, iglob.get(REL, -12000))) + prel) / 1200.0))
        if rels:
            rels.sort()
            out[prog] = (name, rels[len(rels) // 2])
    return out


def _median(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def consensus(programs=PROGRAMS):
    """{program: (median R over the sets, our L, {set: (name, R)})}."""
    per = {name: releases(path, programs) for name, path in SETS if path and os.path.exists(path)}
    out = {}
    for p in programs:
        got = {s: r[p] for s, r in per.items() if p in r}
        if got:
            R = _median([v[1] for v in got.values()])
            out[p] = (R, L_PER_R * R, got)
    return out


def main(argv):
    progs = tuple(int(a) for a in argv[1:]) or PROGRAMS
    sets = [n for n, p in SETS if p and os.path.exists(p)]
    print("  GM  " + "".join("%-22s" % s for s in sets) + "  median R   our L")
    for p, (R, L, got) in sorted(consensus(progs).items()):
        print("  %3d " % p + "".join(("%-15s %5.2f " % (got[s][0][:15], got[s][1])) if s in got else " " * 22
                                    for s in sets) + "  %6.2f s  %5.3f s" % (R, L))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
