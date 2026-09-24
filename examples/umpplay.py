#!/usr/bin/env python3
"""Play a MIDI 2.0 Clip File (or raw UMP stream) to a sequencer port, as UMP.

    python3 live.py --ump --tui                     # in one terminal
    python3 examples/umpplay.py midi2_demo.midi2    # in another

A real MIDI 2.0 sender, in its own process, through the ALSA sequencer: the
same path a MIDI 2.0 controller would take into live. The default destination
is live's port, 'tuning'; --to names any other ('130:0', or a client name).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alsaump  # noqa: E402
import ump as U  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--to", default="tuning", help="destination port (default: live's)")
    a = ap.parse_args()
    evs, facts = U.read(open(a.file, "rb").read())
    c = alsaump.UmpClient("umpplay", "out")
    dest = c.resolve(a.to)
    sys.stderr.write("  %s -> %d:%d, %d UMPs\n" % (os.path.basename(a.file), dest[0], dest[1], len(evs)))
    t0 = time.monotonic() + 0.1
    try:
        for t, pkt in evs:
            d = t0 + t - time.monotonic()
            if d > 0:
                time.sleep(d)
            c.send(pkt, dest)
    except KeyboardInterrupt:
        pass
    finally:
        c.close()


if __name__ == "__main__":
    main()
