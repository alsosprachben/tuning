#!/usr/bin/env python3
"""What MPE lets one keyboard do: an MPE file to hear it by.

    python3 examples/mpe_demo.py [out.mid] [--program 81]
    python3 blockrender.py mpe_demo.mid mpe_demo.wav hybrid440
    python3 live.py --midi2-play mpe_demo.midi2        # after examples/midi1to2.py

MPE (M1-100-UM v1.1): the Lower Zone, manager channel 1 and fifteen member
channels, declared by the MPE Configuration Message first. Every note gets a
member channel of its own and its pitch bend, pressure and CC74 are sent
there, BEFORE its Note On (2.4). Four things, each impossible on one channel:

  1. A C major triad whose E alone slides up a major third to G#, root and
     fifth holding -- a member bend, at the spec's 48-semitone range.
  2. A just-intonation dominant seventh built from member bends alone: E 13.69
     cents flat of equal temperament, G 1.96 sharp, B-flat 31.17 flat (7/4).
  3. A vibrato and a pressure swell on the top note only, the timbre (CC74)
     opening under it.
  4. A manager bend under the whole chord, then the pedal (on the manager) and
     the Note Offs -- and a member bend AFTER its Note Off, which must move
     nothing (2.2.6), where the manager's still moves the ringing chord (A.4.1).

The default voice is the sawtooth lead (81), which answers all three
dimensions; brightness is heard only on voices that have it.
"""
import math
import sys

import mido

TPQ = 480
RANGE = 48.0                     # the member default an MCM sets (2.2.5)


def bend(semitones, rng=RANGE):
    return max(-8192, min(8191, int(round(semitones * 8192 / rng))))


def main(argv):
    out = next((a for a in argv[1:] if not a.startswith('--') and not a.isdigit()), 'mpe_demo.mid')
    prog = int(argv[argv.index('--program') + 1]) if '--program' in argv else 81
    ev = []                      # (tick, message)
    add = lambda tick, m: ev.append((int(tick), m))
    cc = lambda ch, c, v: mido.Message('control_change', channel=ch, control=c, value=v)
    pb = lambda ch, st, rng=RANGE: mido.Message('pitchwheel', channel=ch, pitch=bend(st, rng))
    at = lambda ch, v: mido.Message('aftertouch', channel=ch, value=v)

    def note(tick, ch, n, vel=90, st=0.0, pres=0, tim=64):
        # 2.4: initial values for the three dimensions BEFORE the Note On
        add(tick, pb(ch, st)); add(tick, cc(ch, 74, tim)); add(tick, at(ch, pres))
        add(tick, mido.Message('note_on', channel=ch, note=n, velocity=vel))

    def off(tick, ch, n):
        add(tick, mido.Message('note_off', channel=ch, note=n, velocity=0))

    # the MCM: Lower Zone, 15 members (2.2.1), then the zone's voice
    add(0, cc(0, 101, 0)); add(0, cc(0, 100, 6)); add(0, cc(0, 6, 15))
    add(0, mido.Message('program_change', channel=0, program=prog))
    add(0, cc(0, 7, 100))
    Q = TPQ
    t = Q
    # 1. the E slides a major third, alone
    for ch, n in ((1, 60), (2, 64), (3, 67)):
        note(t, ch, n)
    for i in range(49):
        add(t + 2 * Q + i * 10, pb(2, 4.0 * i / 48.0))
    t += 6 * Q
    for ch, n in ((1, 60), (2, 64), (3, 67)):
        off(t, ch, n)
    # 2. a just dominant seventh, from member bends alone
    t += Q
    just = ((4, 60, 0.0), (5, 64, -0.1369), (6, 67, 0.0196), (7, 70, -0.3117))
    for ch, n, st in just:
        note(t, ch, n, st=st)
    t += 5 * Q
    for ch, n, _ in just:
        off(t, ch, n)
    # 3 and 4. vibrato and swell on the top note; the manager bends the chord;
    # the pedal holds it; a member bend after Note Off moves nothing
    t += Q
    chord = ((8, 55), (9, 60), (10, 64), (11, 72))
    for ch, n in chord:
        note(t, ch, n, pres=0, tim=40)
    steps = 6 * Q // 12
    for i in range(steps):
        tick = t + i * 12
        s = (tick - t) / float(2 * Q)                  # seconds at 120 bpm
        depth = min(1.0, i / (steps / 3.0))
        add(tick, pb(11, 0.25 * depth * math.sin(2 * math.pi * 5.5 * s)))
        swell = math.sin(math.pi * i / steps)
        add(tick, at(11, int(round(110 * swell))))
        add(tick, cc(11, 74, int(round(40 + 80 * swell))))
    t += 6 * Q
    for i in range(25):                                # the manager: the chord sags a tone
        add(t + i * 8, pb(0, -2.0 * math.sin(math.pi * i / 24.0), rng=2.0))
    t += 2 * Q
    add(t, cc(0, 64, 127))                             # the pedal, on the manager
    for ch, n in chord:
        off(t + 10, ch, n)
    add(t + Q, pb(10, 12.0))                           # after Note Off: moves nothing
    add(t + 2 * Q, pb(0, -1.0, rng=2.0))               # the manager: moves the ringing chord
    add(t + 5 * Q, cc(0, 64, 0))
    add(t + 5 * Q, pb(0, 0.0, rng=2.0))
    t += 7 * Q

    ev.sort(key=lambda e: e[0])
    mid = mido.MidiFile(ticks_per_beat=TPQ)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    last = 0
    for tick, m in ev:
        tr.append(m.copy(time=tick - last)); last = tick
    mid.save(out)
    print("wrote %s: %d events, %.1f s, program %d" % (out, len(ev), mid.length, prog))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
