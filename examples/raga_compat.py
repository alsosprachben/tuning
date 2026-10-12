#!/usr/bin/env python3
"""Which Indian tuning sits best with the Western instruments it plays against.

    python3 examples/raga_compat.py FILE.mid --eastern=raga:<system>[/<raga>]@<Sa> [--tuner=hybrid440]
                                             [--auto=et,just5,pythagorean,...]

A secondary tuning (ragas.py, blockrender's eastern=) tunes the Indian
instruments while the rest keep the render's tuner. Where an Indian note sounds
against a Western one, how far apart are they? For every Eastern note and every
Western note sounding WITH it, the Eastern note's pitch against where the
Western tuner puts the SAME key -- the comma or two a sitar's Ga sits from the
piano's E -- weighted by how long they overlap: the beating that would be heard.
Every system is scored with the same Sa (and Sa at the Western tuner's own
pitch for its key, as blockrender places it); the lowest clash first.

--auto=a,b,c prints only the best of those systems, as the spec to render with.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import blockrender as B  # noqa: E402
import patch_map as PM  # noqa: E402
import ragas  # noqa: E402


def notes_of(path):
    """[(channel, note, on, off, program)] from the file, seconds."""
    _, _, notes, *_ = B.parse(path)
    return [(e[0], e[1], e[2], e[3], e[6]) for e in notes]


def indian(prog, ch):
    if ch == 9:
        return False
    return getattr(PM.property_class_for_program(prog), "tuning_family", None) == "indian"


def clash(notes, east_tab, west_tab):
    """(weighted mean |cents|, total overlap s, [(cents, key, seconds)] worst)."""
    E = [n for n in notes if indian(n[4], n[0])]
    W = [n for n in notes if not indian(n[4], n[0]) and n[0] != 9]
    acc, wsum, per = 0.0, 0.0, {}
    for ce, ne, a, b, _ in E:
        for cw, nw, c, d, _ in W:
            ov = min(b, d) - max(a, c)
            if ov <= 0:
                continue
            # the Eastern note against the Western tuner's same key
            cents = 1200.0 * np.log2(east_tab[ne] / west_tab[ne])
            acc += abs(cents) * ov
            wsum += ov
            per[ne % 12] = per.get(ne % 12, 0.0) + ov
    worst = sorted(((1200.0 * np.log2(east_tab[k] / west_tab[k]), k, s)
                    for k, s in ((60 + pc, s) for pc, s in per.items())),
                   key=lambda t: -abs(t[0]) * t[2])[:4]
    return (acc / wsum if wsum else 0.0), wsum, worst


def main(argv):
    path = next((a for a in argv[1:] if not a.startswith("--")), None)
    spec = next((a.split("=", 1)[1] for a in argv if a.startswith("--eastern=")), None)
    tuner = next((a.split("=", 1)[1] for a in argv if a.startswith("--tuner=")), "hybrid440")
    auto = next((a.split("=", 1)[1] for a in argv if a.startswith("--auto=")), None)
    if not path or not spec:
        print(__doc__)
        return 2
    _, raga, key, hz = ragas.parse(spec)
    west = B.tuning_table(tuner)
    notes = notes_of(path)
    allowed = auto.split(",") if auto else sorted(ragas.SYSTEMS)
    rows = []
    for system in allowed:
        s = "raga:%s%s@%s" % (system, "/" + raga if raga else "", spec.split("@", 1)[1].split(":")[0])
        east = ragas.table(s, sa_hz=hz or west.get(ragas.sa_note(key)))
        c, w, worst = clash(notes, east, west)
        rows.append((c, s, w, worst))
    rows.sort()
    if auto:
        print(rows[0][1])
        return 0
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    print("  %s against %s; Eastern notes overlapping Western ones: %.1f s" % (path, tuner, rows[0][2] if rows else 0.0))
    for c, s, w, worst in rows:
        print("  %6.2f cents  %-28s  worst: %s" % (c, s, "  ".join("%s %+.1f (%.1fs)" % (names[k % 12], ct, sec)
                                                             for ct, k, sec in worst)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
