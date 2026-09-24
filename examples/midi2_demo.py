#!/usr/bin/env python3
"""What MIDI 2.0 carries that MIDI 1.0 cannot: a Clip File to hear it by.

    python3 examples/midi2_demo.py [out.midi2]
    python3 live.py --program 19 --midi2-play midi2_demo.midi2

Three things, each impossible in one MIDI 1.0 channel:

  1. A C major triad whose THIRD ALONE settles from equal temperament to the
     just 5:4 (13.69 cents down) while the root and fifth hold -- Pitch 7.25
     sent per note, mid-note, in 64 steps.
  2. The same chord in JUST INTONATION from the first sample: each Note On
     carries its own pitch (the Pitch 7.9 attribute), E at 5/4, G at 3/2.
  3. A vibrato on the TOP NOTE ONLY -- per-note pitch bend -- under a swell on
     a 32-bit CC11 with no seven-bit staircase in it.

It opens with a TUNING TABLE: Pitch 7.25 for every note number, at its own
12-TET pitch (A = 440). That is one of the two uses the spec gives the
message, and it makes the file mean the same under any tuner -- the renderer's
`hybrid` sits at A415, and a MIDI 2.0 pitch is absolute, so without the table
the first move of the third would be a semitone up, not 13.69 cents down.

Everything is written through ump.py, so the file is exactly what a MIDI 2.0
sequencer would send.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ump as U  # noqa: E402

TPQ = 960
Q = TPQ                                 # one beat at 120 bpm = 0.5 s


def main(argv):
    out = argv[1] if len(argv) > 1 else "midi2_demo.midi2"
    ev = []
    add = lambda tick, pkt: ev.append((int(tick), pkt))
    vel = U.scale_up(96, 7, 16)
    add(0, U.m2_cc(0, 0, 7, U.scale_up(100, 7, 32)))
    for n in range(128):
        add(0, U.m2_per_note_ctrl(0, 0, n, U.RPNC_PITCH, U.semitones_to_q(n, 25)))

    # 1. the third settles, root and fifth unmoved
    t = 0
    for n in (60, 64, 67):
        add(t, U.m2_note_on(0, 0, n, vel))
    for i in range(65):
        p = 64 - 0.1369 * i / 64.0
        add(t + 2 * Q + i * (Q // 16), U.m2_per_note_ctrl(0, 0, 64, U.RPNC_PITCH, U.semitones_to_q(p, 25)))
    t += 8 * Q
    for n in (60, 64, 67):
        add(t, U.m2_note_off(0, 0, n, vel))
    # note 64 back to its table pitch for what follows, once it has rung out
    add(t + Q, U.m2_per_note_ctrl(0, 0, 64, U.RPNC_PITCH, U.semitones_to_q(64, 25)))

    # 2. the just chord, each note its own pitch from the first sample
    t += Q
    just = {60: 60.0, 64: 64 + 12 * math.log2(5 / 4) - 4, 67: 67 + 12 * math.log2(3 / 2) - 7}
    for n, p in just.items():
        add(t, U.m2_note_on(0, 0, n, vel, 3, U.semitones_to_q(p, 9)))
    t += 4 * Q
    for n in just:
        add(t, U.m2_note_off(0, 0, n, vel))

    # 3. vibrato on the top note alone, under a 32-bit swell
    t += Q
    for n in (55, 60, 64, 72):
        add(t, U.m2_note_on(0, 0, n, vel))
    add(t, U.m2_rpn(0, 0, 0, 7, U.semitones_to_q(1.0, 25)))     # per-note bend range 1 semitone
    steps = 8 * Q // 24
    for i in range(steps):
        tick = t + i * 24
        depth = min(1.0, i / (steps / 3.0))
        bend = 0.25 * depth * math.sin(2 * math.pi * 5.5 * (tick - t) / (2.0 * Q))
        add(tick, U.m2_per_note_bend(0, 0, 72, int(0x80000000 + bend * 0x7FFFFFFF)))
        swell = 0.35 + 0.65 * math.sin(math.pi * i / steps)
        add(tick, U.m2_cc(0, 0, 11, int(swell * 0xFFFFFFFF)))
    t += 8 * Q
    for n in (55, 60, 64, 72):
        add(t, U.m2_note_off(0, 0, n, vel))
    ev.sort(key=lambda e: e[0])
    U.write_clip(out, ev, tpq=TPQ, us_per_quarter=500000)
    print("wrote %s: %d UMPs, %.1f s" % (out, len(ev), t / TPQ * 0.5))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
