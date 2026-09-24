#!/usr/bin/env python3
"""Convert a Standard MIDI File to MIDI 2.0: a Clip File, or a raw UMP stream.

    python3 examples/midi1to2.py in.mid [out.midi2]        a MIDI Clip File
    python3 examples/midi1to2.py --raw in.mid [out.ump]    a raw UMP stream

Through ump.Midi1to2, the spec's Default Translation (M2-104 Appendix D.3),
merged to one clip in presentation order. Every MIDI 1.0 message keeps a
Delta Clockstamp of its own, so the renderer reads the result at the same
instants to the last bit -- examples/midi2ident.py checks exactly that.
"""
import os
import sys

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ump as U  # noqa: E402


def main(argv):
    raw = "--raw" in argv
    args = [a for a in argv[1:] if a != "--raw"]
    if not args:
        print(__doc__.strip()); return 2
    src = args[0]
    out = args[1] if len(args) > 1 else os.path.splitext(src)[0] + (".ump" if raw else ".midi2")
    slots = U.midi1_to_clip(mido.MidiFile(src, clip=True), out, raw=raw)
    print("wrote %s: %d slots, %d UMPs" % (out, len(slots), sum(len(s[2]) for s in slots)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
