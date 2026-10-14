#!/usr/bin/env python3
"""Write a SoundFont's samples out as wavs named by their root key, so a fit
can read them as recordings (wind_fit.py's staged notes: <note>_<tag>_<i>.wav).

    python3 -I examples/sf2_extract.py BANK.sf2 OUTDIR TAG

Each sample whole, as recorded: a loop is a stretch OF the recording (the
held tone a player keyed), so nothing is tiled -- a fit reads the take as it
was played. Mono 16-bit at the sample's own rate. Prints each sample's name,
root key, length and loop.
"""
import os
import struct
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gm_release import _chunks, _recs  # noqa: E402

NAMES = "C C# D D# E F F# G G# A A# B".split()


def note_name(k):
    return "%s%d" % (NAMES[k % 12], k // 12 - 1)


def main(argv):
    path, out, tag = argv[1], argv[2], argv[3]
    os.makedirs(out, exist_ok=True)
    b = open(path, "rb").read()
    d, smpl = None, None
    for cid, o, sz in _chunks(b, 12, len(b)):
        if cid == b"LIST" and b[o:o + 4] == b"pdta":
            d = {c.decode(): b[oo:oo + s] for c, oo, s in _chunks(b, o + 4, o + sz)}
        if cid == b"LIST" and b[o:o + 4] == b"sdta":
            for c, oo, s in _chunks(b, o + 4, o + sz):
                if c == b"smpl":
                    smpl = oo
    seen = {}
    for s in _recs(d["shdr"], "<20sIIIIIBbHH", 46)[:-1]:
        name = s[0].split(b"\0")[0].decode("latin1")
        root, rate = s[6], s[5]
        i = seen.get(root, 0)
        seen[root] = i + 1
        fn = os.path.join(out, "%s_%s_%d.wav" % (note_name(root), tag, i))
        with wave.open(fn, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b[smpl + 2 * s[1]:smpl + 2 * s[2]])
        print("  %-8s root %3d %-4s %5.2f s  loop %.2f-%.2f s  -> %s" % (
            name, root, note_name(root), (s[2] - s[1]) / rate,
            (s[3] - s[1]) / rate, (s[4] - s[1]) / rate, os.path.basename(fn)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
