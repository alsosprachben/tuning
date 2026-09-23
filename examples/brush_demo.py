"""Eight bars of brushes, for the ear: the Brush set (program 40) has no file
in the corpus that asks for it, so this is what there is to listen to.

    python3 examples/brush_demo.py OUT.mid [PROGRAM]

A medium swing at 132: the swirl held through each bar (note 40), a tap on 2
and 4 (38), a slap to close each four-bar phrase (39), the ride in swing
eighths (51), the pedal hat on 2 and 4 (44) and the kick feathered on all
four (36). PROGRAM 0 renders the same pattern on Standard sticks, for A/B.
"""
import sys

import mido

out = sys.argv[1]
program = int(sys.argv[2]) if len(sys.argv) > 2 else 40
TPB = 480
m = mido.MidiFile(type=1, ticks_per_beat=TPB)
tr = mido.MidiTrack(); m.tracks.append(tr)
tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(132), time=0))
tr.append(mido.Message("program_change", channel=9, program=program, time=0))
ev = []                                   # (tick, on?, note, velocity)


def hit(t, note, vel, dur=TPB // 4):
    ev.append((t, 1, note, vel)); ev.append((t + dur, 0, note, 0))


for bar in range(8):
    b = bar * 4 * TPB
    hit(b, 40, 70, 4 * TPB - 10)          # the swirl, held through the bar
    for beat in range(4):
        t = b + beat * TPB
        hit(t, 36, 38)                    # feathered kick
        hit(t, 51, 78 if beat % 2 else 70)                 # ride, on the beat
        if beat in (1, 3):
            hit(t + 2 * TPB // 3, 51, 60)                  # ...and the swung skip
            hit(t, 44, 64)                                 # pedal hat on 2 and 4
            hit(t, 38 if not (bar % 4 == 3 and beat == 3) else 39,
                72 if not (bar % 4 == 3 and beat == 3) else 100)
ev.sort(key=lambda e: (e[0], e[1]))
now = 0
for t, on, note, vel in ev:
    tr.append(mido.Message("note_on" if on else "note_off", channel=9, note=note,
                           velocity=vel, time=t - now))
    now = t
m.save(out)
print("  wrote %s (program %d)" % (out, program))
