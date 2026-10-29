#!/usr/bin/env python3
"""Half-pedalling, to hear (damper.py): a piano under pedal moves, written
twice -- with the pedal's values, and as the switch it was (the same values
taken at 64: 127 or 0).

    python3 examples/halfpedal_demo.py OUTDIR

writes OUTDIR/halfpedal.mid and OUTDIR/halfpedal_switch.mid. Four gestures,
each a chord or a bass under the pedal, the keys let go, then:

  1. CLEAR      the pedal down to the band's middle: the chord's top thins and
                fades, its body rings on quieter
  2. CATCH      a low C held by the pedal, chords above it changing; between
                them the pedal only half up: each chord's ring cleared, the
                bass still there
  3. FLUTTER    the pedal shaken between full and half: the chord breathing
                down a step at a time instead of stopping
  4. SLOW LIFT  the pedal brought up through the whole band over two seconds:
                the dampers settling, the bass last
"""
import os
import sys

import mido

TPB = 480
BPM = 60.0                       # a beat a second: ticks are easy to read


def sec(t):
    return int(round(t * TPB * BPM / 60.0))


def piece():
    """[(time s, message)] for one track, channel 0, program 0."""
    ev = [(0.0, mido.Message("program_change", program=0))]

    def chord(t0, notes, dur, vel=90):
        for n in notes:
            ev.append((t0, mido.Message("note_on", note=n, velocity=vel)))
            ev.append((t0 + dur, mido.Message("note_off", note=n, velocity=0)))

    def ped(t, v):
        ev.append((t, mido.Message("control_change", control=64, value=int(v))))

    # 1. CLEAR: chord under the pedal, keys up at 1.0, pedal to 64 at 2.0, up at 5.0
    ped(0.2, 127)
    chord(0.5, (48, 55, 60, 64, 67, 72), 0.5)
    ped(2.0, 64)
    ped(5.0, 0)
    # 2. CATCH: a low C, then three chords; between chords the pedal half up
    t = 6.0
    ped(t - 0.1, 127)
    chord(t, (36,), 0.3, 100)
    for i, c in enumerate(((60, 64, 67), (62, 65, 69), (64, 67, 71))):
        tc = t + 1.0 + 1.5 * i
        if i:
            ped(tc - 0.25, 64)       # half up: the chord's ring cleared...
            ped(tc + 0.05, 127)      # ...and down again for the next
        chord(tc, c, 0.6, 80)
    ped(t + 6.0, 0)
    # 3. FLUTTER: a chord, then the pedal shaken full / half four times
    t = 13.0
    ped(t - 0.1, 127)
    chord(t, (48, 52, 55, 60, 64, 67), 0.4, 95)
    for k in range(4):
        ped(t + 1.2 + 0.6 * k, 72)
        ped(t + 1.45 + 0.6 * k, 127)
    ped(t + 4.5, 0)
    # 4. SLOW LIFT: through the band in steps of 4 over two seconds
    t = 19.0
    ped(t - 0.1, 127)
    chord(t, (33, 45, 52, 57, 61, 64, 69), 0.4, 100)
    for k, v in enumerate(range(124, -1, -4)):
        ped(t + 1.0 + 2.0 * k / 31.0, v)
    ev.append((t + 5.0, mido.Message("control_change", control=121, value=0)))
    return sorted(ev, key=lambda e: e[0])


def write(ev, path, switch=False):
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / BPM), time=0))
    last = 0
    for t, msg in ev:
        if switch and msg.type == "control_change" and msg.control == 64:
            msg = msg.copy(value=127 if msg.value >= 64 else 0)
        tk = sec(t)
        tr.append(msg.copy(time=tk - last))
        last = tk
    m.save(path)


def main(argv):
    out = argv[1] if len(argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    ev = piece()
    write(ev, os.path.join(out, "halfpedal.mid"))
    write(ev, os.path.join(out, "halfpedal_switch.mid"), switch=True)
    print("  %s, %s" % (os.path.join(out, "halfpedal.mid"), os.path.join(out, "halfpedal_switch.mid")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
