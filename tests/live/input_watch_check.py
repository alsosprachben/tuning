#!/usr/bin/env python3
"""live.Live's inputs plugged in again (input_watch): python3 tests/live/input_watch_check.py

nvlive's reader opens an input again when it is plugged back in (native/
hostlive.h, midi_reader_ins); live.Live's input_watch does the same with
mido's ports. This runs its one look (_input_watch_step) over names as ALSA
gives them -- a keyboard unplugged, then back under new client:port numbers --
with mido's port opening faked (no device is touched):

  - an open input that goes is closed and remembered; back, it is opened
    again under its new name, and the session is not marked changed
  - one closed on the panel (close_input) while it was gone is not opened again
  - a device that never comes back stays looked for, nothing opened

Exits 1 if any check fails.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
os.environ.setdefault("TUNING_NATIVE_TONE", "off")


class FakePort(object):
    def __init__(self, name):
        self.name, self.closed = name, False

    def close(self):
        self.closed = True


def main():
    import mido
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    opened = []

    def fake_open(name, callback=None):
        p = FakePort(name)
        opened.append(p)
        return p
    mido.open_input = fake_open
    lv = L.Live(program=0, rate=48000, frames=128)
    bad, n = 0, 0

    def check(what, ok, detail=""):
        nonlocal bad, n
        n += 1
        bad += not ok
        print("  %-60s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    old, new = "Moog Messenger:Moog Messenger MIDI 1 24:0", "Moog Messenger:Moog Messenger MIDI 1 28:0"
    lv.open_input(old)
    lv.dirty = False
    gone, back = lv._input_watch_step(["Midi Through:Midi Through Port-0 14:0"])
    check("unplugged: closed and remembered", gone == [old] and not lv.midi_inputs and opened[0].closed
          and list(lv.lost_inputs) == [L.port_key(old)], "%s %s" % (gone, lv.lost_inputs))
    gone, back = lv._input_watch_step(["Midi Through:Midi Through Port-0 14:0"])
    check("still gone: nothing opened", not back and not lv.midi_inputs and len(opened) == 1)
    gone, back = lv._input_watch_step(["Midi Through:Midi Through Port-0 14:0", new])
    check("back under new numbers: opened again", back == [new] and list(lv.midi_inputs) == [new]
          and not lv.lost_inputs, "%s" % back)
    check("...the session not marked changed", lv.dirty is False)
    check("...its label the device's", lv.input_label() == L.port_key(new), lv.input_label())
    lv._input_watch_step([])
    lv.close_input(old)                         # (turned off on the panel while gone)
    lv.close_input(new)
    gone, back = lv._input_watch_step([new])
    check("closed on the panel while gone: not opened again", not back and not lv.midi_inputs
          and not lv.lost_inputs)
    print("input watch: %d checked, %d failed" % (n, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
