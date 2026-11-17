#!/usr/bin/env python3
"""A test piece for the MT-32 modes: what a file written for the unit says
to it, so MT-32: SOUND CANVAS (Init CM-64, its exclusives ignored) and
MT-32: THE UNIT (native/mt32.h, followed) can be heard side by side.
    python3 examples/mt32_demo.py [OUT.mid]      (default ~/Music/mt32/mt32_demo.mid)

Thirteen bars in D minor at 90 (about 35 s), four bars each of:
  A   the chords (channel 2), a harp's arpeggios (3), drums (10)
  A'  + the tune (4), doubled an octave up (5)
  B   the chords move to channel 1 (a System area message), a countermelody
      there; then a last D minor chord.
Channel 1 also carries a soft line from the start: the Sound Canvas plays
it all through (its part 1, a piano); the unit has no part on channel 1
until B moves one there, so there it is silent, then the strings.

Its exclusives, at the start (each one a thing the unit does and a Sound
Canvas does not):
  System area   master volume 90; reverb Hall, time 6 of 8, level 5 of 8
  Patch Memory  program 1 -> Str Sect 1 (on a Sound Canvas: Acou Piano 1)
                program 2 -> custom timbre 1 'Harp' (ours: the GM harp)
                program 3 -> custom timbre 2 'Fr Horn 1' (the MT-32 set's)
  Timbre Memory the two custom timbres' names (only the names: our engine
                plays a custom timbre as the voice nearest its name, so
                this is a test file for it, not one for a real unit)
  Patch Temp    the tune right (part 3), its double left and 10 cents sharp
                (part 4)
  Rhythm Setup  the snare (38) left at level 80, the closed hat (42) right
                at 55
and at B: part 1 onto channel 1. Velocities 40-112, for the MT-32 velocity
switch. One note of the double is written at key 110: the unit folds it an
octave down.
"""
import os
import sys

import mido

TPB = 480
BAR = 4 * TPB


def dt1(addr, data):
    body = list(addr) + list(data)
    return mido.Message('sysex', data=[0x41, 0x10, 0x16, 0x12] + body + [(128 - sum(body) % 128) % 128])


def name10(s):
    return list(s.ljust(10)[:10].encode('ascii'))


def track(name, events):
    """events: (tick, message) -> a track named NAME, in tick order"""
    t = mido.MidiTrack()
    t.append(mido.MetaMessage('track_name', name=name, time=0))
    last = 0
    for tk, m in sorted(events, key=lambda e: e[0]):
        t.append(m.copy(time=tk - last))
        last = tk
    return t


def notes(ch, items, start=0):
    """items: (beat, beats, key, velocity) -> on/off events from tick START"""
    ev = []
    for b, d, k, v in items:
        on = start + int(b * TPB)
        ev.append((on, mido.Message('note_on', channel=ch, note=k, velocity=v)))
        ev.append((on + int(d * TPB) - 10, mido.Message('note_off', channel=ch, note=k, velocity=0)))
    return ev


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser('~/Music/mt32/mt32_demo.mid')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    S = BAR                     # the music starts after a bar of setup
    # THE SETUP: the unit's exclusives, a few ticks apart (as a sequencer sends them)
    setup = [
        dt1((0x10, 0x00, 0x16), [90]),                                  # master volume
        dt1((0x10, 0x00, 0x01), [1, 5, 4]),                             # reverb: Hall, time 6, level 5
        dt1((0x08, 0x00, 0x00), name10('Harp')),                        # custom timbre 1's name
        dt1((0x08, 0x02, 0x00), name10('Fr Horn 1')),                   # custom timbre 2's name
        dt1((0x05, 0x00, 0x00), [0, 48, 24, 50, 12, 0, 1, 0]),          # program 1 -> Str Sect 1
        dt1((0x05, 0x00, 0x08), [2, 0, 24, 50, 12, 0, 1, 0]),           # program 2 -> custom 1 'Harp'
        dt1((0x05, 0x00, 0x10), [2, 1, 24, 50, 12, 0, 1, 0]),           # program 3 -> custom 2 'Fr Horn 1'
        dt1((0x03, 0x00, 0x29), [0]),                                   # part 3: pan right
        dt1((0x03, 0x00, 0x33), [60]),                                  # part 4: fine tune +10 cents
        dt1((0x03, 0x00, 0x39), [14]),                                  # part 4: pan left
        dt1((0x03, 0x01, 0x10 + 4 * (38 - 24) + 1), [80, 14]),          # snare: level 80, left
        dt1((0x03, 0x01, 0x10 + 4 * (42 - 24) + 1), [55, 0]),           # closed hat: level 55, right
    ]
    cond = [(0, mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(90)))]
    cond += [(0, mido.MetaMessage('time_signature', numerator=4, denominator=4))]
    cond += [(10 + 20 * i, x) for i, x in enumerate(setup)]
    cond.append((S + 8 * BAR - 20, dt1((0x10, 0x00, 0x0D), [0])))         # B: part 1 onto channel 1
    m.tracks.append(track('Setup (MT-32 exclusives)', cond))

    prog = lambda ch, p: (S - TPB, mido.Message('program_change', channel=ch, program=p))
    # i  VI  III  VII  (Dm Bb F C), a bar each
    CH = [(50, 53, 57, 62), (46, 50, 53, 58), (45, 48, 53, 57), (43, 48, 52, 55)]
    # the chords: channel 2 (part 1), bars 1-8; a last D minor at bar 13
    ev = [prog(1, 0)]
    for bar in range(8):
        ev += notes(1, [(0, 4, k, 64 + 8 * (bar >= 4)) for k in CH[bar % 4]], S + bar * BAR)
    m.tracks.append(track('Chords (ch 2)', ev))
    # the harp's arpeggios: channel 3 (part 2), all 12 bars
    ev = [prog(2, 1)]
    for bar in range(12):
        c = CH[bar % 4]
        up = [c[0], c[1], c[2], c[3], c[2] + 12, c[3], c[2], c[1]]
        ev += notes(2, [(i * 0.5, 0.5, k + 12, 52 + 6 * (i % 4 == 0)) for i, k in enumerate(up)], S + bar * BAR)
    m.tracks.append(track('Harp (ch 3)', ev))
    # the tune: channel 4 (part 3), bars 5-12; its double an octave up on 5 (part 4)
    TUNE = [  # (beat, beats, key) over four bars
        (0, 1.5, 69), (1.5, 0.5, 74), (2, 1, 77), (3, 1, 76),
        (4, 1.5, 74), (5.5, 0.5, 72), (6, 2, 74),
        (8, 1, 72), (9, 1, 69), (10, 1, 72), (11, 1, 77),
        (12, 3, 76), (15, 1, 79),
    ]
    tune = [(b, d, k, 84 + 14 * (i % 3 == 0) if i < 12 else 112) for i, (b, d, k) in enumerate(TUNE)]
    ev = [prog(3, 2)]
    ev += notes(3, tune, S + 4 * BAR) + notes(3, tune, S + 8 * BAR)
    m.tracks.append(track('Horn (ch 4)', ev))
    ev = [prog(4, 72)]                                    # Flute 1 (the MT-32 set's own, both modes)
    dbl = [(b, d, k + 12, v - 20) for b, d, k, v in tune]
    dbl[-1] = (dbl[-1][0], dbl[-1][1], 110, dbl[-1][3])   # (key 110: the unit folds it to 98)
    ev += notes(4, dbl, S + 4 * BAR) + notes(4, dbl, S + 8 * BAR)
    m.tracks.append(track('Flute (ch 5)', ev))
    # channel 1: a soft line all through (the Sound Canvas's piano); from B,
    # once part 1 listens here, the countermelody on the strings
    ev = [prog(0, 0)]
    for bar in range(8):
        c = CH[bar % 4]
        ev += notes(0, [(0, 1, c[3] + 12, 40), (2, 1, c[2] + 12, 40)], S + bar * BAR)
    COUNTER = [(0, 4, 62), (4, 4, 65), (8, 4, 64), (12, 2, 60), (14, 2, 64)]
    ev += notes(0, [(b, d, k, 70) for b, d, k in COUNTER], S + 8 * BAR)
    ev += notes(0, [(0, 4, k, 70) for k in CH[0]], S + 12 * BAR)
    m.tracks.append(track('Piano / strings (ch 1)', ev))
    # the drums: channel 10, bars 1-12, then the last bar's kick and crash
    ev = []
    for bar in range(12):
        t0 = S + bar * BAR
        for i in range(8):
            ev += notes(9, [(i * 0.5, 0.25, 42, 70 + 20 * (i % 2 == 0))], t0)
        ev += notes(9, [(0, 0.5, 36, 100), (2.5, 0.5, 36, 80), (1, 0.5, 38, 96), (3, 0.5, 38, 104)], t0)
    ev += notes(9, [(0, 2, 36, 110), (0, 4, 49, 100)], S + 12 * BAR)
    m.tracks.append(track('Drums (ch 10)', ev))
    m.save(out)
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
