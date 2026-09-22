#!/usr/bin/env python3
"""The bagpipe through the LIVE path, captured to a file.

Ben, playing it: "Live bagpipe doesn't do the mod control over drones. It does
a vibrato." It did -- live.py knew nothing about `drone_wheel`, so the bagpipe
fell into the catch-all CC1 branch and got 35 cents of vibrato on the one
instrument in the bank that cannot have any.

This drives the live engine headlessly, block by block, exactly as the audio
callback does, so what it writes is what the keyboard plays. Four passes over
the same phrase with the wheel at 0, 42, 85 and 127 -- the chanter alone, then
one tenor, two tenors, and the full set -- and a fifth that stops mid-phrase to
show the bag staying up through a rest and being let down after one.
"""
import os
import sys
import wave

import numpy as np
import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import live as L                                             # noqa: E402

RATE = 48000
FRAMES = 512
BPM = 108

# The nine notes of a Highland chanter, as scotland.py maps them: G4 to A5.
CHANTER = (67, 69, 71, 73, 74, 76, 78, 79, 81)
# The opening of a strathspey-ish figure, in chanter degrees.
PHRASE = [(4, 1.0), (2, 0.5), (4, 0.5), (6, 1.0), (4, 1.0),
          (7, 1.0), (6, 0.5), (4, 0.5), (2, 1.0), (4, 2.0)]


class Capture(object):
    """Run the engine's own callback path with no audio device attached."""

    def __init__(self, program):
        self.lv = L.Live(program=program, rate=RATE, frames=FRAMES,
                         verbose=False)
        self.lv.warm()
        self.out = []

    def blocks(self, seconds):
        n = int(seconds * RATE)
        done = 0
        while done < n:
            n0 = self.lv.n
            self.lv.apply(n0)
            self.lv.sweep(n0)
            self.lv._drone_reap(n0)
            self.lv.slab.reap(n0)
            left, right = self.lv.renderer.render(n0, FRAMES)
            self.lv.n = n0 + FRAMES
            self.out.append(np.stack([self.lv.limit(left),
                                      self.lv.limit(right)], axis=1))
            done += FRAMES

    def send(self, msg):
        self.lv.on_midi(msg)

    def write(self, path):
        a = np.concatenate(self.out, axis=0) if self.out else np.zeros((1, 2))
        pcm = np.clip(a, -1.0, 1.0)
        pcm = (pcm * 2147483647.0).astype("<i4")
        w = wave.open(path, "wb")
        w.setnchannels(2)
        w.setsampwidth(4)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
        w.close()
        self.lv.renderer.close()
        return path


def phrase(cap, beat, rest_after=None):
    """Play PHRASE, optionally holding a silent bar partway through."""
    for i, (deg, beats) in enumerate(PHRASE):
        note = CHANTER[deg]
        cap.send(mido.Message("note_on", channel=0, note=note, velocity=100))
        cap.blocks(beats * beat)
        cap.send(mido.Message("note_off", channel=0, note=note, velocity=0))
        if rest_after is not None and i == rest_after:
            cap.blocks(8.0 * beat)          # two bars: well past part_break_s


def main():
    beat = 60.0 / BPM
    out = os.path.dirname(os.path.abspath(__file__))
    made = []
    for cc in (0, 42, 85, 127):
        cap = Capture(109)
        cap.send(mido.Message("control_change", channel=0, control=1, value=cc))
        cap.blocks(0.25)
        phrase(cap, beat)
        cap.blocks(1.5)
        n = int(round(cc / 127.0 * 3))
        made.append(cap.write(os.path.join(out, "pipes_live_cc%03d.wav" % cc)))
        print("  CC1 %3d -> %d drone%s  %s"
              % (cc, n, "" if n == 1 else "s", os.path.basename(made[-1])))
    cap = Capture(109)
    cap.blocks(0.25)
    phrase(cap, beat, rest_after=4)
    cap.blocks(3.0)
    made.append(cap.write(os.path.join(out, "pipes_live_rest.wav")))
    print("  two bars' rest mid-phrase      %s" % os.path.basename(made[-1]))

    # A BAG HOLDS ONE PRESSURE. The first half hammers the velocity from 30 to
    # 120 and back and must come out dead flat; the second holds one velocity
    # and works CC11, which on a pipe is the only expression there is.
    cap = Capture(109)
    cap.blocks(0.25)
    vels = [30, 60, 90, 120, 100, 70, 45, 120, 35, 110]
    for (deg, beats), vel in zip(PHRASE, vels):
        note = CHANTER[deg]
        cap.send(mido.Message("note_on", channel=0, note=note, velocity=vel))
        cap.blocks(beats * beat)
        cap.send(mido.Message("note_off", channel=0, note=note, velocity=0))
    cap.blocks(1.0)
    swell = [40, 64, 90, 112, 127, 112, 90, 64, 48, 127]
    for (deg, beats), cc in zip(PHRASE, swell):
        note = CHANTER[deg]
        cap.send(mido.Message("control_change", channel=0, control=11, value=cc))
        cap.send(mido.Message("note_on", channel=0, note=note, velocity=100))
        cap.blocks(beats * beat)
        cap.send(mido.Message("note_off", channel=0, note=note, velocity=0))
    cap.blocks(1.5)
    made.append(cap.write(os.path.join(out, "pipes_live_touch.wav")))
    print("  velocity, then CC11            %s" % os.path.basename(made[-1]))
    return made


if __name__ == "__main__":
    main()
