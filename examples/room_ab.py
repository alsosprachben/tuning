"""A solo line for hearing a ROOM, not a piece.

    python3 examples/room_ab.py OUT.mid [PROGRAM]

The early field is what a room does in the first 50-100 ms after each note,
so a piece with a dense texture hides it. This is one violin (PROGRAM 40 by
default): a fast detached run, where every note's early reflections sit in
the gap before the next, then a few long notes with rests between them, where
the room's build-up and decay are heard bare. Used for the early-field change
in roomtail (Kuttruff's reflection density), rendered in each room before and
after.
"""
import sys

import mido

out = sys.argv[1]
program = int(sys.argv[2]) if len(sys.argv) > 2 else 40
TPB = 480
m = mido.MidiFile(type=1, ticks_per_beat=TPB)
tr = mido.MidiTrack(); m.tracks.append(tr)
tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(96), time=0))
tr.append(mido.Message("program_change", channel=0, program=program, time=0))
ev = []
t = 0
run = [67, 69, 71, 72, 74, 76, 78, 79, 81, 79, 78, 76, 74, 72, 71, 69]
for rep in range(2):                      # detached sixteenths, 60% of the slot
    for n in run:
        ev.append((t, 1, n, 84)); ev.append((t + int(TPB / 4 * 0.6), 0, n, 0))
        t += TPB // 4
t += TPB
for n, beats in ((74, 2), (79, 2), (71, 3)):   # long notes, each then a rest
    ev.append((t, 1, n, 76)); ev.append((t + beats * TPB, 0, n, 0))
    t += beats * TPB + 2 * TPB
ev.sort(key=lambda e: (e[0], e[1]))
now = 0
for tk, on, n, v in ev:
    tr.append(mido.Message("note_on" if on else "note_off", channel=0, note=n,
                           velocity=v, time=tk - now))
    now = tk
m.save(out)
print("  wrote %s" % out)
