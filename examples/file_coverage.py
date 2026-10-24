#!/usr/bin/env python3
"""What one MIDI file asks for, against what we cover: each part's tones
(program, bank, the map a GS file's LSB names), its drum sets and the keys it
plays on them, the controllers, RPNs, NRPNs and GS/GM system exclusive it
sends -- each against examples/gm_coverage.py's ratings and the renderer's
own handling.

    python3 -I examples/file_coverage.py FILE.mid

Read as the renderer reads it (blockrender.parse: two-port files as 32
parts), and the raw bank select beside it: a bank we have no tone for falls
back to the capital (patch_map.VariationProgram), which the parse alone would
show as covered.
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import mido                    # noqa: E402

import blockrender as B        # noqa: E402
import gm_coverage as G        # noqa: E402
import patch_map as PM         # noqa: E402
import percussion_map as PCM    # noqa: E402

CC_NAMES = {0: "bank MSB", 1: "modulation", 5: "portamento time", 6: "data entry", 7: "volume",
            10: "pan", 11: "expression", 32: "bank LSB", 38: "data entry LSB", 64: "sustain",
            65: "portamento", 66: "sostenuto", 67: "soft", 71: "resonance", 72: "release",
            73: "attack", 74: "brightness", 84: "portamento control", 91: "reverb send",
            93: "chorus send", 94: "delay send", 98: "NRPN LSB", 99: "NRPN MSB",
            100: "RPN LSB", 101: "RPN MSB", 120: "all sound off", 121: "reset controllers",
            123: "all notes off", 126: "mono", 127: "poly"}


def handled_ccs():
    """The CC numbers blockrender reads: every `cc == N`, `cc in (...)` and
    CC table key in its source (a census, not a proof)."""
    src = open(os.path.join(HERE, "blockrender.py")).read()
    name = r"(?:\bcc|_cc|control|\bcn|\bctl)"
    got = set(int(n) for n in re.findall(name + r"\s*[!=]=\s*(\d+)", src))
    for grp in re.findall(name + r"\s+in\s+\(([\d,\s]+)\)", src):
        got |= set(int(n) for n in grp.replace(" ", "").split(",") if n)
    # ...and a channel's CC table read by number (c.get(11, ...), cc_at(..., 10))
    got |= set(int(n) for n in re.findall(r"\.get\((\d+),\s*(?:T\.)?GM_DEFAULT", src))
    got |= set(int(n) for n in re.findall(r"_at\([^()]*?,\s*(\d+)\s*[,)]", src))
    # ...and the sound controllers, read through a table (tonelib.SOUND_CC)
    import tonelib as _T
    got |= set(_T.SOUND_CC)
    return got


def raw_scan(path):
    """Per part (channel + 16 x port): the (bank MSB, LSB, program) each
    note sounds on, the CCs, RPN/NRPN numbers and sysex addresses sent."""
    mid = mido.MidiFile(path)
    part_of = B.PortedMidi(mid) if any(m.type == "midi_port" for tr in mid.tracks for m in tr) else None
    msgs = []
    for k, tr in enumerate(mid.tracks):
        port, t = 0, 0
        for m in tr:
            t += m.time
            if m.type == "midi_port":
                port = m.port
            msgs.append((t, k, port, m))
    msgs.sort(key=lambda x: (x[0], x[1]))
    bank = collections.defaultdict(lambda: [0, 0])
    prog = collections.defaultdict(int)
    nrpn = collections.defaultdict(lambda: [None, None, None])     # MSB, LSB, which
    tones = collections.defaultdict(collections.Counter)
    ccs = collections.defaultdict(collections.Counter)
    params = collections.Counter()
    sysex = collections.Counter()
    for t, k, port, m in msgs:
        if m.type == "sysex":
            d = tuple(m.data)
            if len(d) >= 7 and d[0] == 0x41 and d[3] == 0x12:
                sysex["GS %02X %02X %02X" % d[4:7]] += 1
            else:
                sysex[" ".join("%02X" % b for b in d[:4])] += 1
            continue
        if not hasattr(m, "channel"):
            continue
        p = m.channel + 16 * (port if part_of else 0)
        if m.type == "control_change":
            ccs[p][m.control] += 1
            if m.control in (0, 32):
                bank[p][0 if m.control == 0 else 1] = m.value
            elif m.control in (99, 98, 101, 100):
                nrpn[p][{99: 0, 98: 1, 101: 0, 100: 1}[m.control]] = m.value
                nrpn[p][2] = "NRPN" if m.control in (99, 98) else "RPN"
            elif m.control == 6 and None not in nrpn[p][:2]:
                params["%s %d,%d" % (nrpn[p][2], nrpn[p][0], nrpn[p][1])] += 1
        elif m.type == "program_change":
            prog[p] = m.program
        elif m.type == "note_on" and m.velocity:
            tones[p][(bank[p][0], bank[p][1], prog[p])] += 1
    return tones, ccs, params, sysex


def main(argv):
    path = argv[1]
    G.variations()                 # fills VAR_RATED in its own order
    G._gs_sets_rated()             # ...and the sets percussion_gs rearranges
    parsed = B.parse(path)
    notes = parsed[2]
    drum_keys = collections.defaultdict(collections.Counter)
    sounding = collections.defaultdict(collections.Counter)
    for n in notes:
        ch, note, pg = n[0], n[1], n[6]
        if B.is_drum(pg):
            drum_keys[(ch, B.kit_for_program(int(pg)))][note] += 1
        else:
            sounding[ch][(int(pg), getattr(pg, "variation", 0))] += 1
    tones, ccs, params, sysex = raw_scan(path)
    gaps = []
    print("== %s: %d notes, %d parts" % (os.path.basename(path), len(notes),
                                         len(set(n[0] for n in notes))))
    print("\nTONES (part: program.variation as sounded -- rating; the raw bank asked)")
    for ch in sorted(sounding):
        for (p, v), cnt in sorted(sounding[ch].items()):
            r = (G.VAR_RATED.get((p, v)) if v else G.RATED.get(p)) or (None, "NOT RATED")
            # a bank this part asked for under program p that never sounded as
            # any variation of p here: it fell back to the capital
            asked = sorted(set((b0, b1) for (b0, b1, pr), _c in tones[ch].items() if pr == p))
            heard = set(vv for (pp, vv) in sounding[ch] if pp == p)
            fell = [a for a in asked if a[0] not in heard and a[0] != 0] if v == 0 else []
            flag = ""
            if fell:
                flag = "  <-- asked bank %s: plays the capital" % ", ".join("%d/%d" % a for a in fell)
                gaps.append("part %d: %d.%s falls back to %d.%d" % (ch + 1, p, "/".join(str(a[0]) for a in fell), p, v))
            if r[0] is None or r[0] < 3:
                gaps.append("part %d: %d.%d rated %s" % (ch + 1, p, v, r[0]))
            print("  %2d (%s%d): %3d.%-3d %5d notes  rating %s  %s%s"
                  % (ch + 1, "AB"[ch // 16], ch % 16 + 1, p, v, cnt, r[0], (r[1] or "")[:70], flag))
    print("\nDRUM SETS (part: set -- keys played, each key's rating)")
    for (ch, kit), keys in sorted(drum_keys.items()):
        own = PCM.KITS.get(kit, {})
        low = []
        for key, cnt in sorted(keys.items()):
            kr = (G.KIT_RATED.get(kit, {}).get(key) if kit else None) or G.PERC_RATED.get(key)
            if key not in own and kit and kit in PCM.KIT_ONLY:
                low.append("%d unmapped" % key)
            elif kr is None:
                low.append("%d unrated" % key)
            elif kr[0] < 3:
                low.append("%d rated %d" % (key, kr[0]))
        for x in low:
            gaps.append("part %d set %d: key %s" % (ch + 1, kit, x))
        print("  %2d: set %3d %-14s %d keys %s" % (ch + 1, kit, PCM.DRUM_SETS.get(kit, "?"), len(keys),
                                                ("-- " + ", ".join(low)) if low else "all rated 3+"))
    print("\nCONTROLLERS (all parts)")
    got = handled_ccs()
    # ...and the insertion effect's control sources (40 03 1B / 1D): any CC the
    # file names there moves the effect (blockrender._efx_cv, gsefx)
    efx_src = set()
    for _t, e in parsed[7][3].get("efx", ()):
        if e[0] == "ctl" and e[1] in (0x1B, 0x1D) and e[2]:
            efx_src.add(int(e[2]))
    got |= efx_src
    tot = collections.Counter()
    for c in ccs.values():
        tot.update(c)
    for cc, cnt in sorted(tot.items()):
        ok = cc in got
        if not ok:
            gaps.append("CC%d (%s) not read" % (cc, CC_NAMES.get(cc, "?")))
        print("  CC%-3d %-20s %6d  %s" % (cc, CC_NAMES.get(cc, "?"), cnt,
                                         ("read (the EFX's control source)" if cc in efx_src else "read")
                                         if ok else "NOT READ"))
    print("\nRPN / NRPN (data entry on)")
    for k, cnt in sorted(params.items()):
        print("  %-14s %5d" % (k, cnt))
    print("\nSYSTEM EXCLUSIVE")
    for k, cnt in sorted(sysex.items()):
        print("  %-14s %5d" % (k, cnt))
    print("\nGAPS: %s" % ("none" if not gaps else ""))
    for g in gaps:
        print("  " + g)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
