#!/usr/bin/env python3
"""Does the native engine read a MIDI file as blockrender.parse does?

    python3 examples/midi_check.py [file.mid ...] [--from=PATH] [options]

native/midi.cpp's reading of each file (native.Midi) against
blockrender.parse's and _prep_notes_off's, with ==: every note (channel,
key, onset, key-up, velocity, CC7/CC11/pan at its onset, program, drum or
not), every controller in message order, the pitch wheel, the file's length.
A file the engine refuses (two ports, a GS exclusive, a bank, an NRPN, MPE,
mono mode: native.MIDI_REFUSED) is counted and left to Python.

Files as prepident's: the corpus (corpus.txt) by default, or --from=PATH (a
list or a folder), --grep=REGEX, --gs. Parsing only: light, no render.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

import bitident as BI       # noqa: E402
import blockrender as B     # noqa: E402
import native as N          # noqa: E402


def python_reading(path):
    r = B.parse(path)
    ccs, total, pws = r[3], r[4], r[6]
    notes = B._prep_notes_off(ccs, r[2])
    return ([(n[0], n[1], n[2], n[3], n[4], tuple(n[5]), int(n[6]), int(B.is_drum(n[6]))) for n in notes],
            {k: list(v) for k, v in ccs.items()}, {k: list(v) for k, v in pws.items()}, total)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    if args:
        files = args
    else:
        pool = opt.get("from")
        if pool and os.path.isdir(pool):
            files = sorted(os.path.join(d, n) for d, _, ns in os.walk(pool) for n in ns
                           if n.lower().endswith((".mid", ".midi")))
        else:
            files = [l.split()[0] for l in open(pool or os.path.join(HERE, "corpus.txt"))
                     if l.strip() and not l.startswith("#")]
        files = BI.select(files, grep=opt.get("grep") or None, gs="gs" in opt)
    same = differ = 0
    refused = {}
    for path in files:
        m = N.Midi(path)
        if m.error:
            why = N.MIDI_REFUSED.get(m.error, m.error)
            refused[why] = refused.get(why, 0) + 1
            continue
        py = python_reading(path)
        c = (m.notes(), m.ccs(), m.pws(), m.total())
        bad = [what for what, a, b in zip(("notes", "controllers", "pitch wheel", "length"), py, c) if a != b]
        if bad:
            differ += 1
            print("  DIFFERS %s: %s" % (os.path.basename(path), ", ".join(bad)))
        else:
            same += 1
    print("native reading: %d files identical, %d differ, refused %s"
          % (same, differ, ", ".join("%d %s" % (n, w) for w, n in sorted(refused.items())) or "none"))
    return differ


if __name__ == "__main__":
    sys.exit(min(main(sys.argv), 255))
